# JetBatang NF

리디바탕(RIDIBatang) 한글을 터미널에서 쓰기 위한 합본 글꼴입니다.
라틴·기호·아이콘은 **JetBrainsMono Nerd Font Mono**, 한글은 **RIDIBatang** 을 씁니다.

![preview](docs/preview.png)

## 왜 합치나

Alacritty 는 글꼴 폴백 목록이 없습니다. `family` 를 하나만 받고, Windows 에서는
DirectWrite 의 시스템 폴백이 동작하므로 한글에 어떤 글꼴이 쓰일지 지정할 수 없습니다.
그래서 한 파일로 합치는 방법밖에 없습니다.

합칠 때 걸리는 건 **글자 폭**입니다. 터미널은 한글을 정확히 2칸으로 세는데,
RIDIBatang 은 한글 advance 가 음절마다 922~963 으로 제각각입니다. 그대로 넣으면
격자가 어긋납니다. 이 저장소의 `build.py` 는 한글 advance 를 라틴 1칸의 정확히
2배(600 → 1200)로 못 박고 칸 중앙에 배치합니다.

## 설치

[Releases](../../releases) 또는 `fonts/` 의 네 파일을 받아 설치한 뒤,
터미널 글꼴을 `JetBatang NF` 로 지정하면 됩니다.

```
JetBatangNF-Regular.ttf
JetBatangNF-Bold.ttf
JetBatangNF-Italic.ttf
JetBatangNF-BoldItalic.ttf
```

**Alacritty** — `alacritty.toml`

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

**Windows Terminal** — `settings.json`

```jsonc
"font": { "face": "JetBatang NF" }
```

**Windows** — 저장소를 받아 아래를 실행하면 설치까지 한 번에 됩니다.

```powershell
powershell -ExecutionPolicy Bypass -File install-windows.ps1
powershell -ExecutionPolicy Bypass -File install-windows.ps1 -Uninstall
```

탐색기에서 우클릭 → 설치를 해도 됩니다. 다만 **파일 복사와 레지스트리 등록만
하는 방식은 쓰지 마세요.** 그렇게 하면 DirectWrite 가 글꼴 가족 목록에는 올리면서
파일로 연결하지 못해, 그 가족을 쓰려는 프로그램이 `GetFont` 에서
`DWRITE_E_FILENOTFOUND`(`0x88985003`) 를 받습니다. Alacritty 는 이때 죽습니다.

```
panicked at dwrote-0.11.5\src\font_family.rs:98:26:
called `Result::unwrap()` on an `Err` value: -2003283965
```

`install-windows.ps1` 은 `AddFontResourceW` 를 부르고 `WM_FONTCHANGE` 를 방송해서
실행 중인 세션도 글꼴을 알아보게 합니다.

**Linux** — `~/.local/share/fonts/` 에 넣고 `fc-cache -fv`

**macOS** — `~/Library/Fonts/` 에 넣기

## 직접 빌드

`fontTools` 만 있으면 됩니다. 재료는 스크립트가 알아서 받습니다.

```sh
pip install fonttools
./build.sh
```

크기나 위치를 바꾸고 싶으면 환경변수로 조절합니다.

```sh
SCALE=1.05 YSHIFT=0 ./build.sh      # 한글을 5% 키우고 원래 높이로
FAMILY="MyBatang NF" ./build.sh     # 글꼴 이름 바꾸기
```

다른 Nerd Font 를 바탕으로 쓸 수도 있습니다.

```sh
NERD_FAMILY=CascadiaCode BASE_PREFIX=CaskaydiaCoveNerdFontMono ./build.sh
```

`build.py` 를 직접 부르면 더 세밀하게 조절할 수 있습니다.

| 옵션 | 기본값 | 설명 |
| --- | --- | --- |
| `--scale` | `1.00` | 한글 배율. `1.00` 이 RIDIBatang 원본 크기 |
| `--yshift` | `60` | 한글 세로 이동. 바탕체는 받침이 깊어 라틴보다 낮게 앉는다 |
| `--shear-from-base` | 꺼짐 | base 의 `italicAngle` 만큼 한글도 기울인다 |
| `--max-err` | `0.001` | 곡선 변환 허용오차(em 비율) |

## 알려진 한계

- **Bold 한글은 굵어지지 않습니다.** RIDIBatang 이 한 굵기만 제공합니다.
  라틴과 아이콘만 굵어집니다.
- **Italic 한글은 가짜 이탤릭**입니다. base 의 기울기만큼 기울인 것입니다.
- 한자가 없습니다. RIDIBatang 에 한자 글리프가 없습니다.
- 힌팅이 없습니다. 아주 작은 크기에서는 명조 특유의 획 대비가 뭉갭니다.

## 라이선스

[SIL Open Font License 1.1](LICENSE). 두 원본 글꼴 모두 같은 license 입니다.

- **JetBrains Mono** — Copyright 2020 The JetBrains Mono Project Authors
- **Nerd Fonts** — Ryan L McIntyre and contributors
- **RIDIBatang** — Copyright (c) 2019 RIDI & Sandoll, 산돌 디자인

"JetBrains Mono" 는 JetBrains s.r.o. 의, "RIDIBatang" 은 리디주식회사의 상표입니다.
이 저장소는 두 회사와 아무 관계가 없으며, 만들어지는 글꼴 이름에도 두 상표를
쓰지 않습니다.
