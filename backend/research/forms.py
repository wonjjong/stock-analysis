from typing import ClassVar

from django import forms


class StockLabForm(forms.Form):
    symbol = forms.RegexField(
        label="종목 티커",
        regex=r"^[A-Za-z0-9.\-]{1,15}$",
        initial="IREN",
        strip=True,
        error_messages={"invalid": "IREN, AAPL, 005930.KS처럼 올바른 티커를 입력해 주세요."},
        widget=forms.TextInput(
            attrs={
                "placeholder": "예: IREN 또는 005930.KS",
                "autocomplete": "off",
                "autocapitalize": "characters",
            }
        ),
    )

    def clean_symbol(self) -> str:
        return self.cleaned_data["symbol"].upper()


class ApiTestForm(forms.Form):
    SERVICE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("DART", "Open DART (한국)"),
        ("SEC", "SEC EDGAR (미국)"),
    ]
    service = forms.ChoiceField(label="서비스", choices=SERVICE_CHOICES, initial="DART")
    identifier = forms.CharField(
        label="종목 식별자 (DART: 종목코드·회사명, SEC: 티커)",
        initial="005930",  # 삼성전자
        widget=forms.TextInput(attrs={"placeholder": "예: 005930, 삼성전자, IREN, NVDA"}),
    )
    year = forms.CharField(
        label="연도 (DART 전용)",
        initial="2023",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "예: 2023"}),
    )

    def clean_identifier(self) -> str:
        """공백만 정리한다. 시장별 해석은 resolver 가 맡는다.

        clean_* 에서 네트워크를 타면 async 뷰의 is_valid() 가 이벤트 루프를 막는다.
        """
        return self.cleaned_data["identifier"].strip()


class StockRankForm(forms.Form):
    """랭킹할 종목 목록. 검색 자동완성이 심볼을 채워 준다."""

    symbols = forms.CharField(
        label="비교할 종목 (쉼표로 구분)",
        initial="005930.KS, 000660.KS, 035420.KS",
        widget=forms.TextInput(
            attrs={"placeholder": "예: 005930.KS, 000660.KS, NVDA", "autocomplete": "off"}
        ),
    )

    # 종목마다 시세를 받아야 해서 개수에 비례해 느려진다. 화면에서 기다릴 만한 선으로 자른다.
    MAX_SYMBOLS = 12

    def clean_symbols(self) -> list[str]:
        raw = self.cleaned_data["symbols"].replace("\n", ",")
        symbols: list[str] = []
        for piece in raw.split(","):
            symbol = piece.strip().upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
        if len(symbols) < 2:
            raise forms.ValidationError("비교하려면 종목이 2개 이상 필요합니다.")
        if len(symbols) > self.MAX_SYMBOLS:
            raise forms.ValidationError(f"한 번에 {self.MAX_SYMBOLS}개까지 비교할 수 있습니다.")
        return symbols
