"""JetBatang NF 를 만드는 코드. 명령줄 입구는 저장소 루트의 build.py 이고, 영역마다 모듈이 하나씩 있다.

    charset   어떤 글자를 RIDIBatang 에서 가져오고, 어떤 글자를 base 글리프로 때울지
    kana      RIDIBatang 에 없는 가나를 있는 가나의 외곽선으로 만들기
    layout    가져온 글자를 base 의 1칸·2칸에 놓는 배율과 위치
    weight    한글 획을 불리거나 깎기. 경계 연산과 그 결과를 믿을 수 있는지 보기
    scanline  경계 연산을 거치지 않고 nonzero 규칙으로 직접 칠해 본 정답
    outlines  외곽선 변환, composite 같은 글리프 공통 도구
    nfd       NFD 로 나뉜 한글 자모·가나를 완성형 글리프로 조합하기
    metadata  이름 테이블, 판 번호, OS/2
    merge     위 단계를 이어 base 에 donor 를 합치는 흐름
    release   굵기 목록, 저장소에 둔 RIDIBatang 경로, build.sh 가 남기는 빌드 기록. 표준 라이브러리만 쓴다
"""
