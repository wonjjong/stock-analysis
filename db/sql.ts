/**
 * SQL 실행기의 구조적 타입만 담는다. 런타임 import가 없으므로 크롤러·인사이트
 * 모듈이 드라이버(`pg`)에 묶이지 않고, esbuild로 파서만 번들하는 테스트도 그대로
 * 동작한다. 구현은 `db/index.ts`의 PgDatabase다.
 */

export type SqlMeta = { changes: number; last_row_id: number | null; rows_read: number };

export interface SqlStatement {
  bind(...params: unknown[]): SqlStatement;
  first<T = Record<string, unknown>>(): Promise<T | null>;
  all<T = Record<string, unknown>>(): Promise<{ success: true; results: T[]; meta: SqlMeta }>;
  run(): Promise<{ success: true; results: unknown[]; meta: SqlMeta }>;
}

export interface SqlDatabase {
  prepare(sql: string): SqlStatement;
  /** 원자적으로 순차 실행한다(한 트랜잭션). */
  batch(statements: SqlStatement[]): Promise<Array<{ success: true; results: unknown[]; meta: SqlMeta }>>;
}
