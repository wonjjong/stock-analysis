import { drizzle } from "drizzle-orm/node-postgres";
import { Pool, type PoolClient, type QueryResult, types } from "pg";
import * as schema from "./schema";

/**
 * 드라이버 기본값은 D1이 주던 값 모양과 다르다. 라우트와 프론트엔드가 이미 정수
 * 밀리초와 number 카운트를 전제로 쓰여 있으므로, 타입 파서를 맞춰 계약을 유지한다.
 * 이걸 안 하면 조용히 형태만 바뀌어 표시가 깨진다(예: COUNT가 문자열이 되어
 * `total.toLocaleString()`이 천단위 구분을 잃는다).
 */
const OID = { INT8: 20, TIMESTAMP: 1114, TIMESTAMPTZ: 1184, DATE: 1082 } as const;

// COUNT(*)는 bigint다. pg는 정밀도 보호를 위해 문자열로 주지만, 이 앱의 카운트는
// 2^53을 넘지 않는다.
types.setTypeParser(OID.INT8, (value) => Number(value));
// timestamptz → 정수 밀리초. D1 시절과 같은 표현이라 호출부를 바꾸지 않아도 된다.
types.setTypeParser(OID.TIMESTAMPTZ, (value) => Date.parse(value));
types.setTypeParser(OID.TIMESTAMP, (value) => Date.parse(`${value}Z`));
// date(published_date_kst)는 'YYYY-MM-DD' 문자열로 둔다. 프론트엔드가 그대로 표시한다.
types.setTypeParser(OID.DATE, (value) => value);

/**
 * D1(SQLite)에서 PostgreSQL로 옮기면서, 호출부 ~30곳이 쓰던 D1 문장 API를 그대로
 * 유지하는 얇은 어댑터를 둔다. 크롤러와 인사이트 파이프라인이 활발히 개발되는 중이라
 * 호출부를 전부 재작성하면 진행 중인 작업과 충돌한다.
 *
 * 재현하는 표면은 실제로 쓰이는 것만이다:
 *   db.prepare(sql).bind(...p).first<T>() | .all<T>() | .run()
 *   db.batch([stmt, ...])            — 한 트랜잭션에서 순차 실행
 *   result.meta.changes              — 영향 행 수
 */

const PLACEHOLDER_SAFE = /'(?:[^']|'')*'|\?/g;

/**
 * D1의 `?` 자리표시자를 Postgres의 `$n`으로 바꾼다. 따옴표 안의 `?`는 건너뛴다.
 *
 * ⚠ jsonb의 존재 연산자도 `?`다(`keywords ? 'x'`). 이 함수는 그것을 자리표시자로
 * 오인하므로 여기서는 쓸 수 없다. 대신 **`@>`(포함) 연산자를 쓴다**:
 *
 *     keywords ? 'x'   →  keywords @> '["x"]'::jsonb
 *
 * `jsonb_exists(keywords,'x')` 함수 형태도 `?`를 피하지만 **GIN 인덱스를 타지 못한다**
 * (측정: `@>`와 `?`는 Bitmap Heap Scan, `jsonb_exists`는 Seq Scan). `@>`는 인덱스를
 * 쓰면서 `?` 문자도 없어 유일하게 양쪽을 만족한다. `jsonb_array_elements_text`로
 * 원소를 펼쳐 LIKE 비교하는 방식도 `?` 충돌은 없으나 인덱스는 쓰지 않는다.
 */
export function toPgPlaceholders(sql: string): string {
  let index = 0;
  return sql.replace(PLACEHOLDER_SAFE, (match) =>
    match === "?" ? `$${++index}` : match,
  );
}

type Meta = { changes: number; last_row_id: number | null; rows_read: number };

function meta(result: QueryResult): Meta {
  return {
    changes: result.rowCount ?? 0,
    last_row_id: (result.rows[0] as { id?: number } | undefined)?.id ?? null,
    rows_read: result.rows.length,
  };
}

export class PgStatement {
  constructor(
    private readonly pool: Pool,
    private readonly sql: string,
    private readonly params: unknown[] = [],
  ) {}

  bind(...params: unknown[]): PgStatement {
    return new PgStatement(this.pool, this.sql, params);
  }

  /** batch()가 같은 커넥션에서 돌리기 위해 쓴다. */
  async execute(runner: Pool | PoolClient): Promise<QueryResult> {
    return runner.query(toPgPlaceholders(this.sql), this.params);
  }

  async first<T = Record<string, unknown>>(): Promise<T | null> {
    const result = await this.execute(this.pool);
    return (result.rows[0] as T | undefined) ?? null;
  }

  async all<T = Record<string, unknown>>() {
    const result = await this.execute(this.pool);
    return { success: true as const, results: result.rows as T[], meta: meta(result) };
  }

  async run() {
    const result = await this.execute(this.pool);
    return { success: true as const, results: result.rows, meta: meta(result) };
  }
}

export class PgDatabase {
  constructor(private readonly pool: Pool) {}

  prepare(sql: string): PgStatement {
    return new PgStatement(this.pool, sql);
  }

  /** D1의 batch는 원자적이다. 한 트랜잭션에서 순차 실행해 그 의미를 유지한다. */
  async batch(statements: PgStatement[]) {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      const out = [];
      for (const statement of statements) {
        const result = await statement.execute(client);
        out.push({ success: true as const, results: result.rows, meta: meta(result) });
      }
      await client.query("COMMIT");
      return out;
    } catch (reason) {
      await client.query("ROLLBACK").catch(() => {});
      throw reason;
    } finally {
      client.release();
    }
  }
}

function connectionString(): string {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL이 없습니다. `.env`에 postgresql://... 형태로 설정하세요. 로컬 개발은 " +
        "`docker compose up -d postgres` 후 postgresql://postgres:postgres@localhost:55432/signalist 를 쓰면 됩니다.",
    );
  }
  return url;
}

// 개발 중 HMR이 모듈을 다시 평가해도 풀이 누적되지 않게 전역에 캐시한다.
const globalForPool = globalThis as unknown as { signalistPool?: Pool };

export function getPool(): Pool {
  if (!globalForPool.signalistPool) {
    globalForPool.signalistPool = new Pool({
      connectionString: connectionString(),
      max: Number(process.env.DATABASE_POOL_MAX ?? 10),
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 10_000,
    });
    // 유휴 커넥션이 서버 쪽에서 끊겨도 프로세스가 죽지 않게 한다.
    globalForPool.signalistPool.on("error", (reason) => {
      console.error("[db] 유휴 커넥션 오류", reason);
    });
  }
  return globalForPool.signalistPool;
}

export function getDb() {
  return drizzle(getPool(), { schema });
}

/**
 * 이름은 D1 시절 그대로 두어 호출부 ~30곳을 건드리지 않는다. 반환값은 이제 Postgres
 * 어댑터다. 뉴스 이관이 끝나면 `getSql()` 같은 이름으로 정리한다.
 */
export function getD1(): PgDatabase {
  return new PgDatabase(getPool());
}

export type SqlDatabase = PgDatabase;
