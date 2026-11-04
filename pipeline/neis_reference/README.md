# NEIS 알레르기 참고 DB

서울(B10) 고등학교를 학교기본정보 API로 조회하여 구 이름 순서로 한 곳씩 순회하고,
각 구 안에서는 학교명·코드 순서로 선택한다. 2026년 9월과 10월 모두 급식이 있는
20개 학교를 사용하며 선택·제외 내역을 남긴다. 서울 전체를 대표하는 통계 표본은 아니다.
조식·중식·석식 등 API가 반환하는 모든 급식구분을 포함한다.

## 실행

Windows 사용자 환경변수 `NEIS_API_KEY`를 사용한다. 인증키를 코드, 요청 URL 로그,
명령행 인자, 결과 파일에 저장하지 않는다. 키가 설정된 로컬 PowerShell에서 실행한다.

```powershell
python pipeline/build_neis_reference.py
```

성공한 학교·월 응답은 캐시하므로 실패 후 같은 명령으로 이어서 수집할 수 있다.
기존 캐시만으로 재생성: `python pipeline/build_neis_reference.py --from-cache`

외부 패키지 없이 표준 라이브러리를 사용한다.
검증: `python pipeline/test_neis_reference.py`

## 산출물

- `reference.sqlite3`: schools, allergens, records, record_allergens, menu_aggregates,
  menu_allergen_stats 테이블. records.source_json에 원문·출처 전체를 보존한다.
- `records.jsonl`: 개별 메뉴별 원본 DDISH_NM, 원본 표시문구, 알레르기 제거 전후 이름,
  학교/교육청 코드·학교명·날짜·급식구분·수집시각·기록 ID를 보존한다.
- `menu_aggregates.json`: 메뉴별 전체 기록 수, 학교 수, 미표기/검토 기록 수,
  학교별 표시 변형, 19종별 표시 학교 수·표시 기록 수·전체 기록 수.
- `allergen_stats.csv`: 위 집계의 평면 표.
- `schools.json`: 실제 선택 학교와 학교기본정보 API 메타데이터.
- `summary.json`, `REPORT.md`: 수집 통계와 학교 간 명시 번호가 다른 메뉴 5개 사례.

임시 API 응답은 `pipeline/_neis_cache/`에 보관하며 Git에서 제외한다.
키 파일(.env), SQLite 생성 중 파일·저널도 제외한다. 최종 DB와 출처 기록은 임시 파일이
아닌 산출물이며 자동으로 Stage/Push하지 않는다.

## 정규화 및 집계 규칙

- `<br>`, `<br/>`, 줄바꿈을 개별 메뉴 경계로 쓴다. `/`, `&`, 쉼표로 복합메뉴를
  임의 분리하지 않는다. 원본 DDISH_NM·개별 줄·줄 번호를 유지한다.
- 숫자와 점/쉼표로 된 괄호에서 1~19 번호를 분리한다. `(70g)` 같은 중량은 보존한다.
  범위 밖 번호·해석되지 않은 숫자 표시는 검토필요로 남기고 확정 표시 집계에서 제외한다.
- 원본 이름은 유지하고 정규화 키에만 Unicode NFKC, 공백 제거, 영문 소문자,
  양끝 별표 제거를 적용한다. `돈까스→돈가스`, `치킨까스→치킨가스`, `생선까스→생선가스`
  외의 추정 동의어는 만들지 않는다. 치즈·새우·소스·브랜드·중량 등은 삭제하지 않는다.
  `치즈돈가스`와 `돈가스`는 별개이며 일부 동일 음식이 별개로 남을 수 있다.
- 학교/날짜/급식구분/DDISH_NM이 모두 같은 API 중복행만 제거한다. 날짜가 다른 반복
  메뉴는 별도 관측이다. 중복 제거 후 메뉴 수는 고유 정규화 키 수다.
- 표시 학교 수는 해당 번호가 명시된 고유 학교 수, 표시 기록 수는 명시된 메뉴 관측 수다.
  메뉴 전체 기록 수에는 미표기와 검토 기록도 포함한다.
- `record_allergens`와 확정 집계에는 `표기` 상태의 번호만 넣는다. 검토필요 행에서 부분
  추출한 후보 번호는 source_json에만 보존한다. 미표기는 음성 관측값으로 쓰지 않는다.

## 해석과 공식 출처

미표기 또는 특정 번호의 비표시는 해당 성분이 없거나 안전하다는 뜻이 아니다.
같은 메뉴명의 표시 차이는 배합·제품·학교 입력 차이일 수 있다. DB의 합집합을 한양대
음식의 확정 알레르기로 적용하지 않는다. 한양대 데이터·추천·웹에는 연결하지 않는다.

- 학교 API: https://open.neis.go.kr/hub/schoolInfo
- 급식 API: https://open.neis.go.kr/hub/mealServiceDietInfo
- API 가이드: https://open.neis.go.kr/portal/guide/apiGuidePage.do
- 번호표 근거(경기도교육청): https://www.goe.go.kr/resource/old/BBSMSTR_000000030174/BBS_202504020145084371.pdf

1 난류 / 2 우유 / 3 메밀 / 4 땅콩 / 5 대두 / 6 밀 / 7 고등어 / 8 게 / 9 새우 /
10 돼지고기 / 11 복숭아 / 12 토마토 / 13 아황산류 / 14 호두 / 15 닭고기 / 16 쇠고기 /
17 오징어 / 18 조개류(굴·전복·홍합 포함) / 19 잣.
