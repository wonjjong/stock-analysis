"""
화면 폼. 검증은 크롤러의 순수 함수를 그대로 쓴다 — 화면과 파이프라인이 같은 규칙을
쓰지 않으면 등록은 되는데 수집이 안 되는 소스가 생긴다.
"""

from __future__ import annotations

from django import forms

from news.crawler.jsurl import InvalidSourceUrl, validate_source_url
from news.crawler.window import DEFAULT_WINDOW_HOURS, MAX_WINDOW_HOURS, MIN_WINDOW_HOURS

CATEGORIES = ("종합", "경제", "증권", "산업", "국제", "정치", "사회", "IT·과학")

HOUR_CHOICES = [(hour, f"{hour:02d}:00") for hour in range(24)]
PAGE_CHOICES = [(n, f"{n}페이지까지") for n in range(1, 11)]
WINDOW_CHOICES = [
    (6, "6시간"), (12, "12시간"), (24, "24시간"), (36, "36시간 (기본)"),
    (48, "48시간 (해외 매체 권장)"), (72, "72시간"), (168, "7일"),
]


class SourceForm(forms.Form):
    """뉴스 소스 등록. `/news/sources` 의 등록 폼."""

    url = forms.CharField(
        label="뉴스 사이트·목록 URL",
        widget=forms.URLInput(attrs={"placeholder": "https://news.example.com/latest"}),
        help_text="RSS·Atom 주소를 넣으면 발행시각이 타임존과 함께 확정적으로 제공되어"
        " HTML 추론보다 정확하고 한 번에 더 많은 기사를 가져옵니다.",
    )
    name = forms.CharField(
        label="소스 이름", required=False, max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "예: Reuters Technology"}),
        help_text="비우면 도메인을 씁니다.",
    )
    category = forms.ChoiceField(
        label="뉴스 분류", choices=[(c, c) for c in CATEGORIES], initial="종합"
    )
    crawl_hour_kst = forms.TypedChoiceField(
        label="매일 수집 시간", choices=HOUR_CHOICES, coerce=int, initial=6,
        help_text="한국시간 기준입니다.",
    )
    max_pages = forms.TypedChoiceField(
        label="목록 페이지 수", choices=PAGE_CHOICES, coerce=int, initial=1,
        help_text="RSS 주소라면 무관합니다. HTML 목록만 있는 사이트에서 올리면"
        " rel=next 또는 번호 페이저를 따라갑니다.",
    )
    window_hours = forms.TypedChoiceField(
        label="수집 기간", choices=WINDOW_CHOICES, coerce=int, initial=DEFAULT_WINDOW_HOURS,
        help_text="한국시간 '오늘'이 아니라 발행 후 경과 시간으로 고릅니다. 해외 매체는"
        " 48시간 이상을 권장합니다.",
    )

    def clean_url(self) -> str:
        """파이프라인과 **같은** 검증을 쓴다. 여기서 통과한 URL 은 수집도 통과한다."""
        try:
            return validate_source_url(self.cleaned_data["url"])
        except InvalidSourceUrl as reason:
            raise forms.ValidationError(str(reason)) from reason

    def clean_window_hours(self) -> int:
        value = self.cleaned_data["window_hours"]
        if not MIN_WINDOW_HOURS <= value <= MAX_WINDOW_HOURS:
            raise forms.ValidationError(
                f"수집 기간은 {MIN_WINDOW_HOURS}~{MAX_WINDOW_HOURS}시간 사이여야 합니다."
            )
        return value


class ProviderForm(forms.Form):
    """AI 공급자 등록. `/news/providers` 의 등록 폼."""

    name = forms.CharField(
        label="이름", max_length=60,
        widget=forms.TextInput(attrs={"placeholder": "예: Google Gemini"}),
    )
    base_url = forms.CharField(
        label="Base URL",
        widget=forms.URLInput(attrs={"placeholder": "https://.../v1"}),
        help_text="OpenAI 호환 엔드포인트의 base URL 입니다. `/chat/completions` 는 붙이지 않습니다.",
    )
    model = forms.CharField(
        label="모델명", max_length=120,
        widget=forms.TextInput(attrs={"placeholder": "gemini-2.5-flash"}),
    )
    api_key = forms.CharField(
        label="API 키",
        widget=forms.PasswordInput(attrs={"placeholder": "발급받은 키"}, render_value=False),
        help_text="DB 에 저장되고 화면·API 응답에는 끝 네 글자만 나갑니다.",
    )
    priority = forms.IntegerField(
        label="우선순위", initial=100, min_value=1, max_value=999,
        help_text="낮은 숫자부터 호출합니다.",
    )
    daily_limit = forms.IntegerField(
        label="일일 한도", initial=0, min_value=0,
        help_text="0 이면 한도를 두지 않습니다. 무료 티어의 일일 요청 수를 적으면 한도에"
        " 닿기 전에 다음 공급자로 넘어갑니다.",
    )

    def clean_base_url(self) -> str:
        return self.cleaned_data["base_url"].rstrip("/")


class ArchiveFilterForm(forms.Form):
    """`/news/archive` 필터. 전부 선택 항목이라 빈 값이 곧 '전체'다."""

    q = forms.CharField(
        label="검색", required=False, max_length=80,
        widget=forms.TextInput(attrs={"placeholder": "제목·요약·분석 내용 검색"}),
    )
    date_from = forms.DateField(
        label="시작일", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    date_to = forms.DateField(
        label="종료일", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    source = forms.IntegerField(label="소스", required=False)
    sentiment = forms.ChoiceField(
        label="감성", required=False,
        choices=[("", "전체"), ("긍정", "긍정"), ("부정", "부정"), ("중립", "중립")],
    )
    symbol = forms.CharField(label="종목", required=False, max_length=20)


class AnalyzeForm(forms.Form):
    """`/news/lab` 즉석 분석. 기사 본문을 붙여넣어 결과를 본다."""

    title = forms.CharField(
        label="기사 제목", max_length=300,
        widget=forms.TextInput(attrs={"placeholder": "기사 제목을 붙여넣으세요"}),
    )
    body = forms.CharField(
        label="기사 본문",
        widget=forms.Textarea(attrs={"rows": 12, "placeholder": "본문을 붙여넣으세요"}),
    )
    use_llm = forms.BooleanField(
        label="AI 공급자로 분석", required=False, initial=True,
        help_text="끄면 규칙 기반으로만 분석합니다. 공급자가 없으면 자동으로 규칙 기반입니다.",
    )
