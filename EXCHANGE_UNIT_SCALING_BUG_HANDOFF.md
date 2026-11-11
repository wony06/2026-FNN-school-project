# 식품교환단위 과다집계 버그 — 작업 핸드오프

> 목적: 이 문서 하나만으로 식품교환단위(교환단위) 과다집계 버그의 원인·수정 범위·검증 방법을 파악해 작업을 이어받을 수 있도록 함. (사전 대화 맥락 없이 읽어도 됨)
> 작성일: 2026-11-09
> 저장소: `2026-FNN-school-project` / 대상 코드: `pipeline/exchange_unit.py`, `pipeline/build_month.py`, `external_exchange_recipes.json`, `custom_exchange_recipes.json`

---

## 0. 한 줄 요약

일부 레시피 기반 항목의 **식품교환단위가 "배치(여러 인분) 레시피 전체량"을 1인분(~71g)에 축소 없이 적용**해 2~9배 폭증한다. **스케일링 코드는 이미 존재**하며, 해당 레시피에 **플래그 한 줄만 추가**하면 대부분 해결된다(코드 재작성 아님). 보조로 버터 등 조미료의 중량 폴백만 손보면 된다.

> ⚠️ 중량 체계(밥/국찌개/생선구이 등)와는 **무관한 별개 버그**다. 중량 작업은 이미 끝났고, 이 문서는 교환단위 서브시스템만 다룬다.

---

## 1. 증상

한 끼 트레이의 교환단위 합이 **30~40**까지 나온다(정상적인 한 끼는 대략 10~20). 항목별로 보면 특정 레시피 항목이 비현실적으로 크다:

| 항목 | 제공량 | 현재 교환단위(합) | 비고 |
|---|---|---|---|
| 마카로니샐러드 | 71 g | **17.1** (지방 10.9) | 71 g 샐러드가 지방 10.9단위(≈55 g 지방) = 불가능 |
| 메밀전병 | 72 g | **21.4** | 72 g 반찬이 21단위 = 불가능 |
| 버터 | 72.2 g | **11.9** (전부 지방) | 버터가 72 g일 리 없음(펫 ~8 g) |

**영향 범위:** 수동보정(`manual_exchange_overrides.json`)으로 덮어둔 68건 외에도, **보정 안 된 공개 트레이 약 60건**(최근 날짜 2026-10-30·11-03·11-11 등 포함)에 동일 과다집계가 그대로 남아 있다. 즉 데이터셋 전반의 선제 버그이고 68건만 임시 패치된 상태다.

> 참고: **영양소(kcal·단백질 등)는 정상**이다. 이 버그는 교환단위 계산 경로에만 있다.

---

## 2. 근본 원인 ① — 배치 레시피 미스케일링 (주범)

### 계산 경로
- 진입점: `pipeline/exchange_unit.py` → `compute_exchange_units(name, weight_g, use_plaza_servings)` (약 L401)
- 레시피 매칭: `_from_external_recipe(name, target_weight_g)` (L310) → `external_exchange_recipes.json` 읽음
  - 같은 구조: `_from_custom_recipe(...)` (L326) → `custom_exchange_recipes.json`
- 두 함수 모두 `scale = _recipe_scale(dish, target_weight_g)`를 구해 각 재료에 `ing["weight_g"] * scale`을 적용한다.

### 문제의 로직 (`_recipe_scale`, L301)
```python
def _recipe_scale(dish, target_weight_g):
    if dish.get("scale_to_target"):
        return target_weight_g / dish["weight_g"]
    ing_sum = sum(ing["weight_g"] for ing in dish["ingredients"])
    if not dish.get("batch_recipe") and abs(dish["weight_g"] - ing_sum) < 5:
        return 1.0                      # ← 완결된 1인분으로 간주하고 재료 그대로 적용
    return target_weight_g / dish["weight_g"]
```

**무엇이 문제인가:**
이 휴리스틱은 "레시피의 `weight_g`가 재료합과 거의 같으면(±5 g) 그건 이미 완결된 1인분이니 그대로 쓴다(scale=1)"는 가정이다. 그런데 **여러 인분짜리 배치 레시피**도 `weight_g = 재료합`(배치 총량)이라서 이 조건에 걸려 **scale=1.0으로 고정**된다. 그 결과 **배치 전체(예: 마카로니샐러드 478 g, 메밀전병 1444 g)의 교환단위가 통째로 1인분에 들어간다.**

### 수정 방법 ① — 플래그 추가 (코드 변경 아님, 데이터 수정)
배치 레시피 항목에 다음 중 하나를 넣으면 된다:
- `"scale_to_target": true` → 항상 `scale = target_weight_g / weight_g`
- `"batch_recipe": true` → 위 "ing_sum≈weight_g ⇒ scale=1" 가드를 건너뛰어 `scale = target_weight_g / weight_g`

둘은 배치 케이스에서 사실상 동일하게 동작한다. **`batch_recipe`가 바로 이 목적(2026-11-04 도입, exchange_unit.py 주석 L297 참조)이라 그걸 쓰는 걸 권장**한다. 이미 여러 커스텀 배치 레시피(크림파스타·미트볼·닭갈비국수 등)가 이 플래그로 정상 작동 중이다.

**스케일 검산 예시** (플래그 추가 후):
- 마카로니샐러드: 배치 478.5 g, 타깃(샐러드 표준) 71 g → scale=71/478.5≈0.148 → 17.1 × 0.148 ≈ **2.5단위** (정상)
- 메밀전병: 배치 1444 g, 타깃(반찬) 72.2 g → scale≈0.050 → 21.4 × 0.050 ≈ **1.1단위** (정상)

### ⚠️ 타깃 중량 주의
`target_weight_g`는 `build_month.py`의 `classify_main_weight`/`classify_side_weight`가 그 항목에 매긴 표준 1인분 중량(예: 샐러드 71 g, 까스 메인 151 g, 일반 반찬 72.2 g)이다. **스케일은 이 타깃이 타당할 때만 올바르다.** 플래그를 켜기 전에 각 항목의 표준중량이 합리적인지 확인하고, 아래 진단 스크립트로 스케일 후 단위를 꼭 눈으로 검산할 것.

---

## 3. 플래그 추가 대상 (전수 점검 결과)

`external_exchange_recipes.json`(13종) + `custom_exchange_recipes.json`(21종)에서 "재료합 == weight_g이고 총량이 큰" 항목을 뽑아 각 `assumptions` 필드로 배치 여부를 판정했다.

### ✅ 확실한 배치 — 플래그 추가 필요
`assumptions`에 "전체 레시피 기준", "N인분", "3쪽=300 g" 등 다인분 배치임이 명시됨.

| 파일 | 레시피 | weight_g | 근거 |
|---|---|---|---|
| external | 마카로니샐러드 | 478 g | 삶은 마카로니 240 g + 마요 75 g… 배치 |
| external | 푸실리샐러드 | 346 g | 삶은 면 240 g… 배치 |
| external | 통살치킨까스 | 470 g | "닭가슴살 3쪽=300 g" (3인분) |
| external | 해장파스타 | 1086 g | 건면+바지락+새우… 대용량 |
| external | 메밀전병 | 1444 g | 물 486 + 김치 200 + 두부 150… |
| external | 순살닭한마리 | 2525 g | "2인분 배합" 명시 |

### ⚠️ 확인 후 판단 (배치 가능성 높음)
| 파일 | 레시피 | weight_g | 확인 포인트 |
|---|---|---|---|
| external | 찹스테이크덮밥 | 688 g | "밥 1공기 210 g" 포함 — 1인분 큰 덮밥인지 vs 1.5인분인지. 타깃 덮밥 418 g 기준 적절한지 |
| external | 돼지고기육전 | 445 g | "돼지 안심 300 g" — 2~3인분 분량으로 보임 |
| custom | 로제마라소스_통합 | 567 g | "첨부 2인분 로제마라샹궈 소스 배합" — 소스만 쓰는데 배치 총량으로 들어감 |

### ❌ 절대 플래그 금지 (의도된 완결 1인분 — scale=1이 정답)
플래그를 켜면 거꾸로 **과소집계**된다.

| 파일 | 레시피 | weight_g | 이유 |
|---|---|---|---|
| external | 돈코츠라멘 | 543 g | exchange_unit.py 주석 L288에 "완결된 1인분"으로 명시됨(면·고명만, 국물 제외한 1그릇) |
| custom | 전복표고솥밥_도라지제외 | 251 g | assumptions에 "완성 밥 250 g을 1인분으로 적용"이라고 명시 |

> 핵심 리스크는 코드가 아니라 **이 "배치 vs 완결 1인분" 판정**이다. 애매하면 `assumptions` 원문을 읽고, 그래도 불확실하면 보류하고 사람에게 물을 것.

---

## 4. 근본 원인 ② — 조미료/스프레드 중량 폴백 (보조)

버터처럼 전용 중량 규칙이 없는 스프레드가 `build_month.py`의 일반 반찬 폴백 `SIDE_FALLBACK`(72.2 g, L244)을 그대로 받아, 고지방 DB에 매칭되면 지방 교환단위가 폭증한다(버터 72.2 g → 지방 11.9단위 ≈ 59 g 지방).

### 수정 방법 ②
`pipeline/build_month.py`에서 택1:
- (a) 버터·마가린·크림치즈·땅콩버터 등 스프레드에 **현실적 소량(펫 ~8 g)** 전용 중량을 준다(소스 9 g 고정과 동일 패턴). 또는
- (b) `compute_tray_exchanges`(L861)의 조미료 제외 목록(약 L876, `돈까스소스`/`브라운소스`… 교환단위 계산에서 skip하는 곳)에 추가해 **자유식품으로 교환단위에서 제외**한다. (잼은 이미 9 g로 처리됨.)

표준 교환표 관례상 소량 유지방은 자유식품 취급이 흔하므로 (b)가 간단하지만, 영양소 탭과의 일관성을 보고 팀에서 결정할 것.

---

## 5. 재현·진단 스크립트

**(A) 보정 미적용(auto) 상태로 과다집계 트레이 찾기 + 항목별 내역**
```python
import json, sys
sys.path.insert(0, 'pipeline')
import build_month as bm
from exchange_unit import compute_exchange_units
GR = ['곡류군','어육류군','채소군','지방군','우유군','과일군']
parsed = json.load(open('pipeline/month_lunch_parsed.json', encoding='utf-8'))
cache = bm.load_cache()
rows = []
for l in parsed:
    t = bm.compute_tray(l, cache)                 # compute_tray는 수동보정 적용 전 순수 auto값
    eu = t.get('식품교환단위') or {}
    s = sum(eu.get(g, 0) for g in GR)
    if s >= 20:
        rows.append((round(s,1), t['date'], t['main'], t['shop'], t['item_detail']))
rows.sort(reverse=True)
for s, d, m, shop, items in rows[:12]:
    print(f'\n[{s}] {d} {shop} {m}')
    for it in items:
        ew = it.get('exchange_weight_g', it['weight_g'])
        r = compute_exchange_units(it['display'], ew, use_plaza_servings=(shop=='105'))
        u = r.get('units', {})
        if sum(u.values()) > 2:
            print(f'   {it["display"]} w={it["weight_g"]} src={r.get("source")} 합={round(sum(u.values()),1)}')
```

**(B) 배치 의심 레시피 감사(플래그 누락 + 총량 큰 것)**
```python
import json
for path, label in [('external_exchange_recipes.json','ext'), ('custom_exchange_recipes.json','custom')]:
    for d in json.load(open(path, encoding='utf-8')):
        w = d.get('weight_g', 0)
        s = sum(i.get('weight_g', 0) for i in d.get('ingredients', []))
        has_flag = d.get('scale_to_target') or d.get('batch_recipe')
        if (not has_flag) and abs(w - s) < 5 and s > 200:
            print(f'{label} {d["name"]:20s} weight_g={w:.0f}  assumptions={(d.get("assumptions") or "")[:90]}')
```

---

## 6. 수정 후 검증

1. 재생성: `python pipeline/build_month.py` → `python pipeline/build_site_data.py`
2. 스크립트 (A)로 **교환단위 합 20 이상 트레이가 정당한 사유 없이는 사라졌는지** 확인.
3. 이전 폭증 항목(마카로니샐러드·메밀전병·버터)이 **1인분 수준(1~3단위)** 으로 내려왔는지 스팟체크.
4. ❌ 목록(돈코츠라멘·전복표고솥밥)이 **과소집계로 떨어지지 않았는지** 역방향 확인.

---

## 7. 수동보정 68건 정리 (마지막 단계)

`manual_exchange_overrides.json`의 68건(날짜 2026-08-24~09-18)은 **바로 이 버그를 우회하려고 교환단위를 손으로 보정해 둔 값**이다. 버그를 고치면:
- 상당수는 자동계산값이 정상으로 돌아와 **보정이 불필요** → 제거 가능.
- 각 건을 재계산값과 비교해 **여전히 차이 나는 것만** 남긴다.
- **보정 파일은 반드시 백업 후** 편집할 것(예: `manual_exchange_overrides.backup-YYYY-MM-DD.json`). preserve 로직은 `pipeline/preserve_manual_data.py`의 `preserved_rows()`/`sync_preserved_exchanges()`에서 적용된다.
- 보정 안 된 ~60건은 버그 수정만으로 자동 정상화된다.

---

## 8. 관련 파일 요약

| 파일 | 역할 | 손댈 곳 |
|---|---|---|
| `pipeline/exchange_unit.py` | 교환단위 계산 엔진 | `_recipe_scale`(L301) 로직 이해용 — **코드 수정 불필요** |
| `external_exchange_recipes.json` | 외부 레시피 13종 | 배치 항목에 `batch_recipe: true` 추가 |
| `custom_exchange_recipes.json` | 커스텀 레시피 21종 | 배치 항목 확인 후 플래그 추가 |
| `pipeline/build_month.py` | 트레이 계산·중량·조미료 제외 | `SIDE_FALLBACK`(L244)/`compute_tray_exchanges`(L861) — 조미료(버터) 처리 |
| `manual_exchange_overrides.json` | 수동보정 68건 | 수정 후 재검토·정리 |
| `pipeline/preserve_manual_data.py` | 보정값 보존 로직 | 동작 이해용 |

---

## 9. 작업 규모 요약
- **코드 변경:** 사실상 1곳(버터/조미료 중량). 스케일링 엔진은 이미 존재.
- **데이터 변경:** 레시피 ~6~9종에 플래그 한 줄씩 (+ 각 `assumptions` 확인).
- **시간 비중:** 대부분은 **검증 + 68건 보정 처분 결정**(계산보다 판단).
- **리스크:** 낮음~중간. 플래그 메커니즘은 기존 배치 레시피에서 검증됨. 유일한 핵심 리스크는 "배치 vs 완결 1인분" 오판(돈코츠라멘·전복솥밥을 건드리지 말 것).
