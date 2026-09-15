# JetBatang NF

[JetBrainsMono Nerd Font Mono](https://github.com/ryanoasis/nerd-fonts) 에
[RIDIBatang](https://ridicorp.com/ridibatang/) 한글을 합친 글꼴입니다.
라틴·기호·아이콘은 Nerd Font 쪽에서, 한글과 가나는 RIDIBatang 에서 가져옵니다.
한글 advance 는 라틴 1칸의 정확히 두 배로 맞춰 넣어 터미널 격자가 어긋나지 않습니다.

굵기 여덟 단계 × 정체·이탤릭, 모두 열여섯 종입니다.

**Alacritty (Regular / Bold)**
![preview](docs/preview.png)

**굵기 여덟 단계**
![weights](docs/weights.png)

**터미널 크기별**
![sizes](docs/sizes.png)

## 왜 합치나

Alacritty 는 글꼴 폴백 목록이 없습니다. `family` 를 하나만 받으니 한 파일로 합치는
수밖에 없습니다. 문제는 글자 폭인데, RIDIBatang 은 한글 advance 가 음절마다
922~963 으로 제각각이라 그대로 넣으면 격자가 깨집니다. `build.py` 가 이걸 1200
(라틴 600 의 2배)으로 못 박고 칸 중앙에 배치합니다.

## 설치

[Releases](../../releases) 에서 원하는 굵기의 `ttf` 나 `JetBatangNF-all.zip` 을
받으세요. 저장소 `fonts/` 에는 기본 네 종만 들어 있습니다. 설치한 뒤 터미널 글꼴을
`JetBatang NF` 로 지정하면 됩니다.

**Windows**

```powershell
powershell -ExecutionPolicy Bypass -File install-windows.ps1
powershell -ExecutionPolicy Bypass -File install-windows.ps1 -Uninstall
```

탐색기 우클릭 → 설치도 됩니다. 다만 **파일 복사와 레지스트리 등록만 하는 방식은
쓰지 마세요.** DirectWrite 가 가족 목록에는 올리면서 파일로 연결하지 못해,
Alacritty 가 `DWRITE_E_FILENOTFOUND`(`0x88985003`) 를 받고 죽습니다.

```
panicked at dwrote-0.11.5\src\font_family.rs:98:26:
called `Result::unwrap()` on an `Err` value: -2003283965
```

**Linux** — `~/.local/share/fonts/` 에 넣고 `fc-cache -fv`

**macOS** — `~/Library/Fonts/` 에 넣기

**Alacritty**

```toml
[font.normal]
family = "JetBatang NF"
style = "Regular"

[font.bold]
family = "JetBatang NF"
style = "Bold"

[font.italic]
family = "JetBatang NF"
style = "Italic"
```

## 빌드

`fontTools` 만 있으면 됩니다. 재료는 스크립트가 알아서 받습니다.

```sh
pip install fonttools
./build.sh
```

결과는 `fonts/JetBatangNF-*.ttf` 열여섯 개입니다.

```sh
SCALE=1.05 YSHIFT=0 ./build.sh       # 한글을 5% 키우고 원래 높이로
EMBOLDEN_SCALE=1.25 ./build.sh       # 한글 굵기 증가량을 25% 더
FAMILY="MyBatang NF" ./build.sh      # 글꼴 이름 바꾸기

NERD_FAMILY=CascadiaCode BASE_PREFIX=CaskaydiaCoveNerdFontMono ./build.sh
```

한 종씩 세밀하게 조절하려면 `python3 build.py --help` 를 보세요.

## 굵기 구성

RIDIBatang 은 세로획 80 짜리 한 굵기뿐입니다. 굵은 쪽은 한글 외곽선을 여덟 방향으로
겹쳐 획을 불리고, **Regular 보다 가는 쪽은 한글을 그대로 둡니다.** Thin·ExtraLight·
Light 는 라틴만 가늘어집니다.

| 굵기 | `style` | 파일 | 라틴 세로획 | 한글 세로획 |
| --- | --- | --- | --- | --- |
| Thin | `Thin` / `Thin Italic` | `JetBatangNF-Thin`, `-ThinItalic` | 50 | 82 |
| ExtraLight | `ExtraLight` / `ExtraLight Italic` | `JetBatangNF-ExtraLight`, `-ExtraLightItalic` | 66 | 82 |
| Light | `Light` / `Light Italic` | `JetBatangNF-Light`, `-LightItalic` | 79 | 82 |
| Regular | `Regular` / `Italic` | `JetBatangNF-Regular`, `-Italic` | 90 | 82 |
| Medium | `Medium` / `Medium Italic` | `JetBatangNF-Medium`, `-MediumItalic` | 99 | 91 |
| SemiBold | `SemiBold` / `SemiBold Italic` | `JetBatangNF-SemiBold`, `-SemiBoldItalic` | 108 | 100 |
| Bold | `Bold` / `Bold Italic` | `JetBatangNF-Bold`, `-BoldItalic` | 125 | 117 |
| ExtraBold | `ExtraBold` / `ExtraBold Italic` | `JetBatangNF-ExtraBold`, `-ExtraBoldItalic` | 150 | 140 |

세로획 값은 1000 upem 기준, `한` 의 세로획을 잰 것입니다.

## 적용 범위

바탕은 `JetBrainsMonoNerdFontMono` 하나만 씁니다. 이미 Nerd Font 패치본이라 패치를
다시 돌리지 않습니다. RIDIBatang 에서 가져오는 건 터미널이 2칸으로 세는 구간뿐이고,
나머지는 base 가 이미 고정폭이라 건드리지 않습니다.

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

장음부호 `ー`(`U+30FC`)는 RIDIBatang 에 없어서 같은 모양인 `―`(`U+2015`) 를 씁니다.
없으면 `コーヒー` 가 `コ□ヒ□` 로 깨집니다. `build.py` 의 `ALIASES` 에 있습니다.

## 눈으로 확인하기

```text
JetBatang NF 테스트 ABC abc 0123456789
가각간갇갈감갑값같꿇뷁힣
한글과 English 가 섞인 주석 한 줄
if (상태 === "완료") return "성공";
ㄱㄴㄷㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣ
ひらがな カタカナ コーヒー データ サーバー
（）［］｛｝，．：；！？ ㈜ ㎡ ￦
```

## 알려진 한계

- 13px 아래에서는 굵은 쪽 한글의 속공간이 메워집니다. `뷁` 부터 뭉갭니다.
- 한자가 없습니다. RIDIBatang 에 한자 글리프가 없습니다.
- 가나 중 `ゔ ゕ ゖ ゛ ゜ ゝ ゞ ヷ ヸ ヹ ヺ ヽ ヾ` 등 열아홉 자가 없습니다.
- 힌팅이 없습니다. 아주 작은 크기에서는 명조 특유의 획 대비가 뭉갭니다.

## 라이선스

[SIL Open Font License 1.1](LICENSE). 두 원본 글꼴 모두 같은 license 입니다.

- **JetBrains Mono** — Copyright 2020 The JetBrains Mono Project Authors
- **Nerd Fonts** — Ryan L McIntyre and contributors
- **RIDIBatang** — Copyright (c) 2019 RIDI & Sandoll, 산돌 디자인

"JetBrains Mono" 는 JetBrains s.r.o. 의, "RIDIBatang" 은 리디주식회사의 상표입니다.
이 저장소는 두 회사와 아무 관계가 없으며, 만들어지는 글꼴 이름에도 두 상표를
쓰지 않습니다.
