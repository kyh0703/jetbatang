# JetBatang NF

터미널에서 쓰는 한글 명조 글꼴이에요. [JetBrainsMono Nerd Font Mono](https://github.com/ryanoasis/nerd-fonts) 의
라틴·기호·아이콘에 [RIDIBatang](https://ridicorp.com/ridibatang/) 의 한글·가나를 얹었어요.
한글 글자폭은 라틴의 정확히 두 배(1200/600)로 고정해서, 한글을 섞어 써도 격자가 어긋나지 않아요.
굵기 여덟 단계에 정체와 이탤릭을 더해 모두 열여섯 종이에요.

![preview](docs/preview.png)

![weights](docs/weights.png)

![sizes](docs/sizes.png)

```text
JetBatang NF 테스트 ABC abc 0123456789
가각간갇갈감갑값같꿇뷁힣
한글과 English 가 섞인 주석 한 줄
if (상태 === "완료") return "성공";
ㄱㄴㄷㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣ
ひらがな カタカナ コーヒー データ サーバー
（）［］｛｝，．：；！？ ㈜ ㎡ ￦
```

## INSTALL

[Releases](../../releases) 에서 원하는 굵기의 `ttf` 나 `JetBatangNF-all.zip` 을 받으세요.
저장소 `fonts/` 에도 열여섯 종이 모두 들어 있어요. 설치한 뒤 터미널에서 글꼴 이름을 `JetBatang NF` 로 지정하면 돼요.

**Windows**

```powershell
powershell -ExecutionPolicy Bypass -File install-windows.ps1
powershell -ExecutionPolicy Bypass -File install-windows.ps1 -Uninstall
```

탐색기 우클릭 → 설치도 돼요. 다만 파일 복사와 레지스트리 등록만 하는 설치 방식은 쓰지 마세요.
DirectWrite 가 글꼴 목록에는 올려두고 정작 파일은 찾지 못해요. 그래서 글꼴을 요청한 프로그램이
`DWRITE_E_FILENOTFOUND`(`0x88985003`) 를 받고 실패해요.

**Linux** — `~/.local/share/fonts/` 에 넣고 `fc-cache -fv`

**macOS** — `~/Library/Fonts/` 에 넣기

## WEIGHTS

| 굵기 | `style` | 파일 | 라틴 세로획 | 한글 세로획 |
| --- | --- | --- | --- | --- |
| Thin | `Thin` / `Thin Italic` | `JetBatangNF-Thin`, `-ThinItalic` | 50 | 82 |
| ExtraLight | `ExtraLight` / `ExtraLight Italic` | `JetBatangNF-ExtraLight`, `-ExtraLightItalic` | 66 | 82 |
| Light | `Light` / `Light Italic` | `JetBatangNF-Light`, `-LightItalic` | 79 | 82 |
| Regular | `Regular` / `Italic` | `JetBatangNF-Regular`, `-Italic` | 90 | 82 |
| Medium | `Medium` / `Medium Italic` | `JetBatangNF-Medium`, `-MediumItalic` | 99 | 90 |
| SemiBold | `SemiBold` / `SemiBold Italic` | `JetBatangNF-SemiBold`, `-SemiBoldItalic` | 108 | 100 |
| Bold | `Bold` / `Bold Italic` | `JetBatangNF-Bold`, `-BoldItalic` | 125 | 118 |
| ExtraBold | `ExtraBold` / `ExtraBold Italic` | `JetBatangNF-ExtraBold`, `-ExtraBoldItalic` | 150 | 138 |

표의 세로획 값은 1000 upem 기준으로 `한` 의 세로획을 잰 거예요.

RIDIBatang 은 세로획 80 짜리 한 굵기밖에 없어요. 그래서 Regular 이하는 한글을 그대로 두고
라틴만 가늘어져요. Medium 부터는 한글 외곽선을 여덟 방향으로 겹쳐 획을 불린 다음,
겹친 외곽선을 하나로 합쳐요. 불리는 양은 가로 방향을 기준으로 잡고, 세로 방향은 그 0.4 배만 줘요.

## COVERAGE

베이스 글꼴은 `JetBrainsMonoNerdFontMono` 하나만 써요. RIDIBatang 에서 가져오는 건
터미널이 2칸으로 세는 구간뿐이고, 나머지는 베이스를 그대로 둬요.

| 구간 | 내용 |
| --- | --- |
| `U+AC00`–`U+D7A3` | 한글 완성형 |
| `U+3130`–`U+318F` | 한글 호환 자모 |
| `U+3041`–`U+309F` | 히라가나 |
| `U+30A0`–`U+30FF` | 가타카나 |
| `U+3000`–`U+303F` | CJK 문장부호 `。、「」〜` |
| `U+3200`–`U+32FF` | 괄호문자·원문자 `㈜ ㉠ ㎡` |
| `U+FF01`–`U+FF60` | 전각 영숫자·기호 |
| `U+FFE0`–`U+FFE6` | 전각 통화기호 `￦` |

RIDIBatang 에는 장음부호 `ー`(`U+30FC`) 가 없어요. 그대로 두면 `コーヒー` 가 `コ□ヒ□` 로
깨지기 때문에, 모양이 같은 `―`(`U+2015`) 를 대신 써요. `build.py` 의 `ALIASES` 에 있어요.

## LIMITATIONS

- 13px 아래에서는 굵은 쪽 한글의 속공간이 메워져요. `뷁` 같은 글자부터 뭉개지기 시작해요.
- 한자가 없어요. 원본인 RIDIBatang 에 한자 글리프가 없어서예요.
- 가나 중 `ゔ ゕ ゖ ゛ ゜ ゝ ゞ ヷ ヸ ヹ ヺ ヽ ヾ` 등 열아홉 자가 빠져 있어요.
- 힌팅이 없어요. 아주 작은 크기에서는 명조 특유의 획 대비가 뭉개져요.

## BUILD

`fontTools` 와 `skia-pathops` 가 필요해요. 원본 글꼴은 스크립트가 알아서 내려받아요.

```sh
pip install fonttools skia-pathops
./build.sh
```

결과는 `fonts/JetBatangNF-*.ttf` 열여섯 개예요.

```sh
SCALE=1.05 YSHIFT=0 ./build.sh       # 한글을 5% 키우고 원래 높이로
EMBOLDEN_SCALE=1.25 ./build.sh       # 한글 굵기 증가량을 25% 더
FAMILY="MyBatang NF" ./build.sh      # 글꼴 이름 바꾸기

NERD_FAMILY=CascadiaCode BASE_PREFIX=CaskaydiaCoveNerdFontMono ./build.sh
```

한 종씩 세밀하게 조절하려면 `python3 build.py --help` 를 보세요.

## LICENSE

[SIL Open Font License 1.1](LICENSE). 원본 글꼴 두 개 모두 같은 라이선스예요.

- **JetBrains Mono** — Copyright 2020 The JetBrains Mono Project Authors
- **Nerd Fonts** — Ryan L McIntyre and contributors
- **RIDIBatang** — Copyright (c) 2019 RIDI & Sandoll, 산돌 디자인

"JetBrains Mono" 는 JetBrains s.r.o. 의, "RIDIBatang" 은 리디주식회사의 상표예요.
이 저장소는 두 회사와 아무 관계가 없고, 만들어 내는 글꼴 이름에도 두 상표를 쓰지 않아요.
