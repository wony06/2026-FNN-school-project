(function () {
  "use strict";

  const MEALS = {breakfast: "아침", lunch: "점심", dinner: "저녁", snack: "간식"};
  const KINDS = {cooked: "조리식품", recipe: "기존 레시피 계산값", processed: "가공식품", ingredient: "식품 원재료·성분표"};
  const MACROS = {
    carb: {name: "탄수화물", factor: 4, range: [0.50, 0.65]},
    protein: {name: "단백질", factor: 4, range: [0.10, 0.20]},
    fat: {name: "지방", factor: 9, range: [0.15, 0.30]},
  };
  const NUTRIENTS = ["kcal", ...Object.keys(MACROS)];
  const STORAGE = "hyu-menu-guide.meal-diary.v1";
  const datePattern = /^\d{4}-\d{2}-\d{2}$/;
  const number = new Intl.NumberFormat("ko-KR", {maximumFractionDigits: 1});
  const fmt = value => number.format(value);
  const valueOrNull = value => Number.isFinite(value) && value >= 0 ? value : null;
  const readNumber = input => valueOrNull(input.valueAsNumber);
  const escape = value => String(value ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[ch]);

  function seoulDate() {
    const fields = new Intl.DateTimeFormat("en", {
      timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
    }).formatToParts(new Date());
    const part = type => fields.find(field => field.type === type).value;
    return [part("year"), part("month"), part("day")].join("-");
  }

  function diaryTargets(context) {
    if (!context) return null;
    const kcal = context.goal === "weight_loss" ? context.adjustedEer : context.eer;
    return {
      kcal,
      ranges: Object.fromEntries(Object.entries(MACROS).map(([key, macro]) => [
        key, macro.range.map(fraction => kcal * fraction / macro.factor),
      ])),
      highProtein: context.goal === "high_protein" ? context.weightKg * 1.2 : null,
      weightLoss: context.goal === "weight_loss",
    };
  }

  function totals(records) {
    const amounts = {};
    for (const key of NUTRIENTS) {
      let known = 0;
      let available = 0;
      let partial = false;
      for (const record of records) {
        const value = valueOrNull(record.nutrients?.[key]);
        if (value !== null) {
          known += value;
          available++;
        }
        if (value === null || record.incomplete?.includes(key)) partial = true;
      }
      amounts[key] = {known, partial, available};
    }
    return amounts;
  }

  function foodReference(food) {
    if (!food) return null;
    if (!food.basis && Number.isFinite(food.grams) && food.grams > 0) {
      return {amount: food.grams, unit: "g"};
    }
    let basis = String(food.basis ?? "").normalize("NFKC").trim();
    basis = basis.replace(/^1\s*회(?:\s*제공량)?\s*:?\s*/u, "");
    if (basis.startsWith("(") && basis.endsWith(")")) basis = basis.slice(1, -1).trim();
    const match = /^(\d+(?:\.\d+)?)\s*(g|ml)$/i.exec(basis);
    const amount = match ? Number(match[1]) : null;
    if (!Number.isFinite(amount) || amount <= 0) return null;
    return {amount, unit: match[2].toLowerCase() === "ml" ? "mL" : "g"};
  }

  function basisLabel(food, reference) {
    return reference ? `기준량 ${reference.amount} ${reference.unit}` : food.basis;
  }

  function entryUnit(entry) {
    return entry.unit ?? "g"; // All previously saved measured amounts were in grams.
  }

  function recordedAmount(entry) {
    return entry.amount === null ? "섭취량 미확인" : `${entry.amount} ${entryUnit(entry)}`;
  }

  function scale(food, amount, unit) {
    const reference = foodReference(food);
    if (amount !== null && (!reference || unit !== reference.unit)) return null;
    const factor = amount === null ? 1 : amount / reference.amount;
    const nutrients = Object.fromEntries(NUTRIENTS.map(key => {
      const value = valueOrNull(food.nutrients[key]);
      return [key, value === null ? null : value * factor];
    }));
    return Object.values(nutrients).every(value => value === null || Number.isFinite(value)) ? nutrients : null;
  }

  function cafeteriaFood(row) {
    const incomplete = new Set(row.unmatched?.length ? NUTRIENTS : []);
    for (const field of row.missingFields ?? []) {
      const keys = field.slice(field.lastIndexOf(":") + 1).trim().split(/\s*,\s*/);
      for (const key of keys) if (NUTRIENTS.includes(key)) incomplete.add(key);
    }
    for (const detail of row.itemDetails ?? []) {
      if (detail.matched === false) NUTRIENTS.forEach(key => incomplete.add(key));
      for (const key of detail.missing ?? []) if (NUTRIENTS.includes(key)) incomplete.add(key);
    }
    return {
      id: row.sourceMenuId || [row.date, row.shop, row.category, row.main].join("|"),
      kind: "cafeteria",
      name: row.main,
      source: row.shopName || "한양대 학생식당",
      detail: [row.date, row.category].filter(Boolean).join(" · "),
      grams: Number.isFinite(row.weight) && row.weight > 0 ? row.weight : null,
      nutrients: Object.fromEntries(NUTRIENTS.map(key => [key, valueOrNull(row[key])])),
      incomplete: [...incomplete],
      excluded: Boolean(row.allergyAssessment?.excluded),
    };
  }

  function databaseFood(row) {
    const [id, name, source, detail, foodType, basis, ...values] = row;
    return {
      id, name, source, detail, foodType, basis, kind: id.split(":")[0],
      nutrients: Object.fromEntries(NUTRIENTS.map((key, i) => [key, valueOrNull(values[i])])),
      incomplete: row[10]?.incomplete ?? [],
      recipeNote: row[10]?.note ?? null,
    };
  }

  function mount() {
    const el = id => document.getElementById(id);
    const tabList = el("mealServiceTabs");
    const recommend = el("mealRecommendationPanel");
    const diary = el("mealDiaryPanel");
    const dialog = el("mealEntryDialog");
    const form = el("mealEntryForm");
    const date = el("mealDiaryDate");
    const consent = el("mealDiaryConsent");
    const entryDate = el("mealEntryDate");
    const entryMeal = el("mealEntrySlot");
    const amountInput = el("mealEntryAmount");
    const search = el("mealFoodQuery");
    const searchResults = el("mealFoodResults");
    const scrollPositions = {recommendation: 0, diary: 0};
    const today = seoulDate();
    date.value = today;
    date.max = today;
    entryDate.max = today;
    let records = [];
    let context = null;
    let table = null;
    let tableFailed = false;
    let worker = null;
    let searchId = 0;
    let searchTimer;
    let editor;
    let opener;
    let confirmation;

    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE));
      if (saved?.consent === true && Array.isArray(saved.records)) {
        records = saved.records.filter(record => record && typeof record.id === "string" &&
          datePattern.test(record.date) && Object.hasOwn(MEALS, record.meal) &&
          typeof record.name === "string" && record.nutrients &&
          ["database", "manual", "cafeteria"].includes(record.mode));
        consent.checked = true;
      }
    } catch {
      el("mealDiaryStatus").textContent = "저장한 기록을 불러올 수 없습니다.";
    }

    function persist(revoke = false) {
      try {
        if (consent.checked) localStorage.setItem(STORAGE, JSON.stringify({consent: true, records}));
        else if (revoke) localStorage.removeItem(STORAGE);
        el("mealDiaryStatus").textContent = consent.checked
          ? "이 브라우저에 기록을 저장합니다." : "현재 이용 중에만 기록이 유지됩니다.";
      } catch {
        consent.checked = false;
        el("mealDiaryStatus").textContent = "브라우저 저장소를 사용할 수 없어 현재 이용 중에만 기록이 유지됩니다.";
      }
    }

    function selectTab(name, focus = false) {
      const diaryActive = name === "diary";
      const previous = diary.hidden ? "recommendation" : "diary";
      if (previous !== name) scrollPositions[previous] = window.scrollY;
      recommend.hidden = diaryActive;
      diary.hidden = !diaryActive;
      for (const tab of tabList.querySelectorAll("[role=tab]")) {
        const selected = tab.dataset.mealTab === name;
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
        if (focus && selected) tab.focus({preventScroll: true});
      }
      if (diaryActive) render();
      if (previous !== name) window.scrollTo({top: scrollPositions[name], behavior: "instant"});
    }

    function amountLabel(entry) {
      if (entry.mode === "manual") return "직접 입력 · 추정 열량";
      const amount = recordedAmount(entry);
      if (entry.mode === "cafeteria") {
        return (entry.portion === "serving" ? "학식 추정 1인분 · " : "학식 g 환산 · ") + amount;
      }
      return (entry.portion === "serving" ? "1인분 적용 · " : "") + amount;
    }

    function sumLabel(amount, unit) {
      if (amount.partial && !amount.available) return "미확인";
      return `${fmt(amount.known)} ${unit}`;
    }

    function nutrientText(values) {
      return NUTRIENTS.map(key => {
        const unit = key === "kcal" ? "kcal" : "g";
        const label = key === "kcal" ? "열량" : MACROS[key].name;
        const value = values[key];
        return label + " " + (value === null ? "미확인" : fmt(value) + " " + unit);
      }).join(" · ");
    }

    function bar(amount, lower, upper, range = true) {
      const scaleMax = range ? Math.max(upper * 1.2, amount.known, 1) : upper;
      const position = Math.min(100, 100 * amount.known / scaleMax);
      const start = 100 * lower / scaleMax;
      const end = 100 * upper / scaleMax;
      const zone = range ? `<i class="meal-range-zone" style="left:${start}%;width:${end - start}%"></i>` : "";
      return `<div class="meal-meter" aria-hidden="true">${zone}<i class="meal-meter-fill" style="width:${position}%"></i></div>`;
    }

    function renderMacroBreakdown(total) {
      const parts = Object.entries(MACROS).map(([key, macro]) => ({
        key, name: macro.name, amount: total[key], kcal: total[key].known * macro.factor,
      }));
      const macroKcal = parts.reduce((sum, part) => sum + part.kcal, 0);
      const hasShare = Number.isFinite(macroKcal) && macroKcal > 0;
      let boundary = 0;
      const segments = hasShare ? parts.map(part => {
        const start = boundary;
        boundary = Math.min(100, boundary + part.kcal / macroKcal * 100);
        return `var(--meal-${part.key}) ${start}% ${boundary}%`;
      }).join(", ") : "";
      const legend = parts.map(({key, name, amount, kcal}) => {
        const share = amount.partial && !amount.available ? "미확인" :
          hasShare ? fmt(kcal / macroKcal * 100) + "%" : "—";
        return `<li><span><i class="meal-macro-dot meal-macro-${key}"></i>${name}</span><strong>${share}</strong></li>`;
      }).join("");
      return `<figure class="meal-breakdown">
        <figcaption>탄단지 열량 비율 <small>확인된 영양정보 기준</small></figcaption>
        <div class="meal-donut" aria-hidden="true"${hasShare ? ` style="--meal-donut-fill:conic-gradient(${segments})"` : ""}>
          <span>${hasShare ? `<strong>${fmt(macroKcal)}</strong><small>환산 kcal</small>` : "<small>표시할 비율 없음</small>"}</span>
        </div>
        <ul class="meal-breakdown-legend" aria-label="탄단지 열량 비율">${legend}</ul>
      </figure>`;
    }

    function renderMacroCard(key, macro, amount, range, energy) {
      const ratio = !energy.partial && !amount.partial && energy.known > 0
        ? fmt(amount.known * macro.factor / energy.known * 100) + "%" : "—";
      let badge = "";
      let state = "unknown";
      let primary = "목표 범위 미설정";
      let secondary = "";
      if (range) {
        const [lower, upper] = range;
        if (amount.known > upper) {
          state = "above";
          badge = "초과";
          primary = `상한보다 ${fmt(amount.known - upper)} g 초과`;
        } else if (amount.known < lower) {
          state = "below";
          badge = "부족";
          primary = `하한까지 ${fmt(lower - amount.known)} g 남음`;
          secondary = `상한까지 ${fmt(upper - amount.known)} g 여유`;
        } else {
          state = "within";
          badge = "적정";
          primary = "적정 범위예요";
          secondary = `상한까지 ${fmt(upper - amount.known)} g 여유`;
        }
      }
      if (amount.partial) {
        if (range && state === "above") primary = "확인된 값만으로 " + primary;
        else if (range && state === "within") primary = "확인된 값 기준 적정 범위";
        else primary = amount.available ? "확인된 값 기준으로 표시해요" : "확인된 섭취량이 없어요";
        secondary = `일부 음식의 ${macro.name} 정보가 미확인되어 참고용으로 표시돼요.`;
        state = "unknown";
        badge = "일부 미확인";
      }
      const quantity = amount.partial && !amount.available ? "—" : fmt(amount.known);
      return `<article class="meal-macro">
        <div class="meal-macro-head"><h4>${macro.name}</h4>${badge ? `<span class="meal-macro-badge is-${state}">${badge}</span>` : ""}</div>
        <p class="meal-macro-value"><strong>${quantity}</strong> g${amount.partial && amount.available ? " · 확인된 값" : ""}</p>
        <p>목표 범위 ${range ? fmt(range[0]) + "–" + fmt(range[1]) + " g" : "—"}</p>
        ${range ? bar(amount, ...range) : ""}
        <p class="meal-macro-status">${primary}</p>
        ${secondary ? `<p>${secondary}</p>` : ""}
        ${ratio !== "—" ? `<p class="meal-macro-ratio">기록 열량 대비 ${ratio}</p>` : ""}
      </article>`;
    }

    function renderSummary(entries) {
      const total = totals(entries);
      const targets = diaryTargets(context);
      const energy = total.kcal;
      const goal = targets?.kcal;
      let energyNote = "기본 정보와 영양 목표를 입력하면 목표를 확인할 수 있어요.";
      let noteClass = "";
      if (goal && energy.partial) {
        energyNote = "일부 음식의 열량이 미확인되어 확인된 값만 보여줘요.";
      } else if (goal) {
        const left = goal - energy.known;
        noteClass = left < 0 ? "is-above" : "is-within";
        if (left < 0) energyNote = `<strong>${fmt(-left)} kcal</strong> 초과했어요`;
        else if (left > 0) energyNote = `<strong>${fmt(left)} kcal</strong> 더 먹을 수 있어요`;
        else energyNote = "오늘 목표 열량에 도달했어요";
      }
      const recorded = energy.partial && !energy.available ? "—" : fmt(energy.known);
      el("mealEnergySummary").innerHTML = `
        <p class="meal-kicker">하루 총섭취 열량</p>
        <div class="meal-energy-values">
          <div class="meal-energy-number"><small>${energy.partial ? "확인된 섭취량" : "현재 섭취량"}</small><strong>${recorded}</strong> kcal</div>
          <div class="meal-energy-goal"><small>하루 목표</small><strong>${goal ? fmt(goal) : "—"}</strong> kcal</div>
        </div>
        ${goal ? bar(energy, 0, goal, false) : ""}
        <p class="meal-energy-note ${noteClass}">${energyNote}</p>
        ${targets?.weightLoss ? '<p class="meal-muted">기존 체중감량 설정의 조정 열량입니다. 낮은 목표 열량은 적절한지 확인해주세요.</p>' : ""}`;
      const cards = Object.entries(MACROS).map(([key, macro]) =>
        renderMacroCard(key, macro, total[key], targets?.ranges[key], energy));
      el("mealMacroSummary").innerHTML = `${renderMacroBreakdown(total)}<div class="meal-macro-grid">${cards.join("")}</div>`;
      const high = el("mealProteinTarget");
      high.hidden = targets?.highProtein == null;
      if (!high.hidden) {
        const above = targets.highProtein > targets.ranges.protein[1];
        const amount = total.protein;
        const status = amount.partial ? "일부 음식의 단백질 정보가 미확인되어 남은 양을 확정하기 어려워요." :
          amount.known >= targets.highProtein ? "하루 고단백 목표에 도달했어요." :
          `고단백 목표까지 ${fmt(targets.highProtein - amount.known)} g 남았어요.`;
        high.textContent = `하루 고단백 목표 ${fmt(targets.highProtein)} g (체중 × 1.2 g/kg). ${status} ${above ? "이 목표는 일반 단백질 적정 범위 상한(에너지의 20%)보다 높습니다. " : ""}일반 단백질 적정 범위와 별개의 서비스 목표입니다.`;
      }
    }

    function renderRecordChips(record) {
      const chips = [];
      if (record.mode !== "manual") {
        chips.push(`<span>${recordedAmount(record)}</span>`);
      }
      for (const [key, label, unit] of [["kcal", "", "kcal"], ["carb", "탄", "g"], ["protein", "단", "g"], ["fat", "지", "g"]]) {
        const amount = valueOrNull(record.nutrients[key]);
        chips.push(`<span>${label ? label + " " : ""}${amount === null ? (label ? "미확인" : "열량 미확인") : fmt(amount) + " " + unit}</span>`);
      }
      return `<div class="meal-record-chips">${chips.join("")}</div>`;
    }

    function renderMeals(entries) {
      el("mealDiaryMeals").innerHTML = Object.entries(MEALS).map(([key, label]) => {
        const group = entries.filter(record => record.meal === key);
        const total = totals(group);
        const partial = NUTRIENTS.some(nutrient => total[nutrient].partial);
        const rows = group.map(record => {
          const source = record.mode === "manual" ? "직접 입력 · 추정 열량" :
            [record.base?.source, record.mode === "cafeteria" ? "추정 영양값" : "",
              record.portion === "serving" ? "1인분" : ""].filter(Boolean).join(" · ");
          const incomplete = record.incomplete?.length || NUTRIENTS.some(nutrient => valueOrNull(record.nutrients[nutrient]) === null);
          return `<li class="meal-record">
            <div class="meal-record-head">
              <strong>${escape(record.name)}</strong>
              <div class="meal-record-actions"><button type="button" data-meal-edit="${escape(record.id)}" aria-label="${escape(record.name)} 수정">수정</button>
              <button type="button" data-meal-delete="${escape(record.id)}" aria-label="${escape(record.name)} 삭제">삭제</button></div>
            </div>
            ${renderRecordChips(record)}
            <p>${escape(source)}${incomplete ? " · 일부 미확인 (확인된 값 기준)" : ""}</p>
            ${record.base?.excluded ? '<p>알레르기 근거로 추천에서 제외된 메뉴</p>' : ""}</li>`;
        }).join("");
        const subtotal = `<div class="meal-slot-total">
          <span>식사 소계${partial ? " · 확인된 값 기준" : ""}</span>
          <strong>${sumLabel(total.kcal, "kcal")}</strong>
          <div>탄 ${sumLabel(total.carb, "g")} <span aria-hidden="true">·</span> 단 ${sumLabel(total.protein, "g")} <span aria-hidden="true">·</span> 지 ${sumLabel(total.fat, "g")}</div>
        </div>`;
        return `<section class="meal-card meal-slot"><div class="meal-slot-head"><h3>${label}</h3><button type="button" class="meal-outline" data-meal-add="${key}">+ 음식 추가</button></div>
          ${group.length ? subtotal + `<ul class="meal-records">${rows}</ul>` : '<p class="meal-muted">아직 기록한 음식이 없습니다.</p>'}</section>`;
      }).join("");
    }

    function render() {
      const entries = records.filter(record => record.date === date.value);
      renderSummary(entries);
      renderMeals(entries);
      el("mealDiaryClear").disabled = records.length === 0;
    }

    function updateMode(mode) {
      editor.mode = mode;
      el("mealEntryDatabase").hidden = mode !== "database";
      el("mealEntryManual").hidden = mode !== "manual";
      el("mealEntryMode").hidden = mode === "cafeteria";
      el("mealEntryActualRow").hidden = mode !== "cafeteria";
      for (const button of el("mealEntryMode").querySelectorAll("button")) {
        button.setAttribute("aria-pressed", String(button.dataset.entryMode === mode));
      }
      updatePreview();
    }

    function activeServingInfo() {
      const reference = foodReference(editor.food);
      if (editor.mode === "cafeteria") return reference
        ? {state: "available", ...reference, label: "기존 학식 추정량"} : {state: "unknown_basis"};
      if (!reference) return {state: "unknown_basis"};
      const original = editor.original;
      if (!editor.reapplyServing && original?.base?.id === editor.food.id && original.portion === "serving" &&
          entryUnit(original) === reference.unit && Number.isFinite(original.amount) && original.amount > 0) {
        return {...original.servingReference, state: "available", amount: original.amount,
          unit: reference.unit, label: original.servingReference?.label ?? "기록 당시 1인분", preserved: true};
      }
      return MealServing.lookup(editor.food, table);
    }

    function activeServing() {
      const serving = activeServingInfo();
      return serving.state === "available" ? serving.amount : null;
    }

    function currentEntry() {
      const mode = editor.mode;
      const base = editor.food;
      const portion = form.elements.portion.value;
      let name, amount, nutrients;
      let unit = null;
      if (mode === "manual") {
        name = el("mealManualName").value.trim();
        if (!name) return null;
        nutrients = Object.fromEntries(Object.keys(MACROS).map(key => [key, readNumber(el("mealManual-" + key))]));
        if (Object.values(nutrients).some(value => value === null)) return null;
        nutrients.kcal = Object.entries(MACROS).reduce((sum, [key, macro]) => sum + nutrients[key] * macro.factor, 0);
        if (!Number.isFinite(nutrients.kcal)) return null;
        amount = null;
      } else {
        const reference = foodReference(base);
        if (!base || (mode === "database" && !reference)) return null;
        name = base.portionName || base.name;
        unit = reference?.unit ?? null;
        amount = portion === "serving" ? activeServing() : readNumber(amountInput);
        if (portion === "direct" && (!reference || !amount)) return null;
        if (mode === "database" && !amount) return null;
        nutrients = scale(base, amount, unit);
        if (!nutrients) return null;
      }
      return {
        date: entryDate.value, meal: entryMeal.value, mode, name, amount, unit,
        portion: mode === "manual" ? null : portion,
        nutrients, base: mode === "manual" ? null : base,
        ...(mode === "database" && portion === "serving" ? {servingReference: activeServingInfo()} : {}),
        incomplete: NUTRIENTS.filter(key => nutrients[key] === null || (mode !== "manual" && base.incomplete?.includes(key))),
      };
    }

    function duplicates(candidate) {
      if (candidate.mode !== "cafeteria") return false;
      return records.some(record => record.date === candidate.date && record.mode === "cafeteria" &&
        record.base?.id === candidate.base.id && record.id !== editor.original?.id);
    }

    function updatePreview() {
      const {mode, food} = editor;
      const reference = foodReference(food);
      const unit = reference?.unit ?? "g";
      const servingInfo = activeServingInfo();
      const serving = servingInfo.state === "available" ? servingInfo.amount : null;
      const servingOption = el("mealPortionServing");
      const directOption = el("mealPortionDirect");
      const servingAvailable = mode === "cafeteria" || Boolean(serving);
      servingOption.closest("label").hidden = false;
      servingOption.disabled = !servingAvailable;
      directOption.closest("label").hidden = !reference;
      el("mealEntryPortions").hidden = mode === "manual" || !food;
      const servingAmount = serving ? ` · ${serving} ${unit}` : "";
      el("mealServingLabel").textContent = mode === "cafeteria"
        ? "기존 추정 1인분" + (servingAmount || " · 중량 미확인")
        : "1인분 적용" + (servingAmount || " · 기준 없음");
      el("mealDirectLabel").textContent = `직접 입력(${unit})`;
      el("mealAmountLabel").textContent = `섭취량(${unit})`;
      if (servingOption.checked && !servingAvailable) directOption.checked = true;
      el("mealAmountField").hidden = mode === "manual" || !reference || !directOption.checked;
      el("mealServingHint").textContent = mode === "database" && reference
        ? servingInfo.state === "available"
          ? "실제 섭취량이 다르면 직접 입력해주세요"
          : servingInfo.state === "unit_unavailable"
            ? `${servingInfo.label}에는 ${unit} 표준량이 없습니다. g·mL를 환산하지 않고 ${unit}로 직접 입력해주세요.`
            : servingInfo.state === "extra_noodles"
              ? `추가면(사리)은 자동 1인분 적용 대상에서 제외합니다. 실제 먹은 양을 ${unit}로 직접 입력해주세요.`
              : `1인분 정보 없음${tableFailed ? " · 기준표 로딩 실패" : ""}. DB 기준과 같은 ${unit}로 직접 입력해주세요. g·mL는 임의 환산하지 않습니다.`
        : mode === "cafeteria" && reference ? "g 입력 시 한 끼 전체 추정 영양값을 중량에 비례해 환산합니다." : "";
      el("mealEntrySource").textContent = mode !== "manual" && food
        ? [food.name, food.source, food.detail, mode === "database" ? basisLabel(food, reference) : ""].filter(Boolean).join(" · ") : "";
      el("mealEntryWarning").textContent = mode === "cafeteria" && food.excluded
        ? "알레르기 근거로 추천에서 제외된 메뉴입니다. 이 기록은 실제 섭취 여부만 남깁니다." : "";
      const candidate = currentEntry();
      el("mealEntryPreview").textContent = candidate
        ? `${amountLabel(candidate)} · ${nutrientText(candidate.nutrients)}${candidate.incomplete.length ? " · 일부 영양값은 미확인 또는 부분 합계입니다." : ""}`
        : "음식과 섭취량을 입력하면 저장할 영양정보를 확인할 수 있어요.";
      const duplicate = candidate && duplicates(candidate);
      const duplicateKey = duplicate ? candidate.date + "|" + candidate.base.id : null;
      if (confirmation !== duplicateKey) el("mealEntryDuplicate").checked = false;
      confirmation = duplicateKey;
      el("mealEntryDuplicateRow").hidden = !duplicate;
      el("mealEntrySave").disabled = !candidate || !datePattern.test(entryDate.value) ||
        entryDate.value > today || (mode === "cafeteria" && !el("mealEntryActual").checked) ||
        (duplicate && !el("mealEntryDuplicate").checked);
    }

    function openEntry({record, meal = "lunch", food, button}) {
      opener = button;
      form.reset();
      clearTimeout(searchTimer);
      searchId++;
      searchResults.replaceChildren();
      el("mealSearchStatus").textContent = "";
      editor = {original: record, food: food || record?.base || null, mode: "database"};
      confirmation = null;
      entryMeal.value = record?.meal || meal;
      entryDate.value = record?.date || date.value || today;
      el("mealEntryTitle").textContent = record ? "음식 기록 수정" : food ? "먹은 학식 기록" : "음식 추가";
      if (record?.mode === "manual") {
        el("mealManualName").value = record.name;
        for (const key of Object.keys(MACROS)) el("mealManual-" + key).value = record.nutrients[key] ?? "";
      }
      el("mealEntryActual").checked = Boolean(record?.mode === "cafeteria");
      el("mealPortionServing").checked = record?.portion === "serving" || Boolean(food);
      el("mealPortionDirect").checked = !el("mealPortionServing").checked;
      const reference = foodReference(editor.food);
      amountInput.value = record && entryUnit(record) === reference?.unit ? record.amount ?? "" : "";
      updateMode(record?.mode || (food ? "cafeteria" : "database"));
      dialog.showModal();
    }

    function renderSearch({groups, ordered, counts, error, recipeUnavailable, portionQuery, matchedQuery}) {
      searchResults.replaceChildren();
      el("mealSearchStatus").textContent = error || (Object.values(counts).some(Boolean)
        ? "이름 일치와 출처 우선순위로 정렬했습니다. 기준량·출처를 확인하고 선택해주세요. 유형별 최대 20건을 표시합니다." + (recipeUnavailable ? " 레시피 후보는 불러오지 못했습니다." : "")
        : "검색 결과가 없습니다. 다른 이름으로 검색하거나 직접 입력해주세요.");
      if (error) return;
      for (const [kind, rows] of ordered ? [[null, ordered]] : Object.entries(groups)) {
        if (!rows.length) continue;
        const heading = document.createElement("h4");
        heading.textContent = `${KINDS[kind]} · ${fmt(counts[kind])}건`;
        if (kind) searchResults.append(heading);
        for (const row of rows) {
          const food = databaseFood(row);
          // Preserve only the explicit mini modifier, never an unrelated fuzzy menu.
          if (portionQuery && MealServing.normalize(food.name) === MealServing.normalize(matchedQuery)) food.portionName = portionQuery;
          const button = document.createElement("button");
          button.type = "button";
          button.className = "meal-search-result";
          const reference = foodReference(food);
          button.disabled = !reference;
          const details = [food.source, food.detail, basisLabel(food, reference), food.id.split(":").slice(1).join(":")];
          if (food.portionName) details.push(`${food.portionName} 분량 기준`);
          if (!reference) details.push("g·mL 기준량 미확인");
          const standard = MealServing.lookup(food, table);
          details.push(standard.state === "available" ? `1인분 ${standard.amount} ${standard.unit} (${standard.label})` : "1인분 기준 없음");
          if (food.incomplete.length) details.push("일부 영양값 미확인");
          button.innerHTML = `<strong>${escape(food.name)}</strong><small>${escape(details.filter(Boolean).join(" · "))}</small>`;
          button.addEventListener("click", () => {
            editor.food = food;
            editor.reapplyServing = true;
            amountInput.value = "";
            el("mealPortionServing").checked = Boolean(activeServing());
            el("mealPortionDirect").checked = !el("mealPortionServing").checked;
            searchResults.replaceChildren();
            el("mealSearchStatus").textContent = "";
            updatePreview();
            (el("mealPortionServing").checked ? el("mealPortionServing") : amountInput).focus();
          });
          searchResults.append(button);
        }
      }
    }

    function runSearch() {
      const query = search.value.trim();
      const id = ++searchId;
      searchResults.replaceChildren();
      if (!query) {
        el("mealSearchStatus").textContent = "";
        return;
      }
      el("mealSearchStatus").textContent = "음식 DB에서 검색 중…";
      try {
        if (!worker) {
          worker = new Worker("./meal-food-search.js?v=category-20261112");
          worker.onmessage = ({data}) => {
            if (data.id === searchId && dialog.open && editor.mode === "database") renderSearch(data);
          };
          worker.onerror = () => {
            worker.terminate();
            worker = null;
            if (dialog.open) renderSearch({error: "음식 검색을 사용할 수 없습니다. 직접 영양정보를 입력해주세요."});
          };
        }
        worker.postMessage({id, query});
      } catch {
        renderSearch({error: "음식 검색을 사용할 수 없습니다. 직접 영양정보를 입력해주세요."});
      }
    }

    tabList.addEventListener("click", event => {
      const tab = event.target.closest("[data-meal-tab]");
      if (tab) selectTab(tab.dataset.mealTab);
    });
    tabList.addEventListener("keydown", event => {
      const tab = event.target.closest("[data-meal-tab]");
      if (!tab || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const name = event.key === "Home" ? "recommendation" : event.key === "End" ? "diary" :
        tab.dataset.mealTab === "diary" ? "recommendation" : "diary";
      selectTab(name, true);
    });
    date.addEventListener("change", () => {
      if (!date.value || date.value > today) date.value = today;
      render();
    });
    consent.addEventListener("change", () => persist(!consent.checked));
    el("mealDiaryClear").addEventListener("click", () => {
      if (!window.confirm("모든 날짜의 식사 기록을 삭제할까요?")) return;
      records = [];
      persist();
      render();
    });
    el("mealDiaryMeals").addEventListener("click", event => {
      const button = event.target.closest("button");
      if (!button) return;
      if (button.dataset.mealAdd) openEntry({meal: button.dataset.mealAdd, button});
      if (button.dataset.mealEdit) {
        const record = records.find(entry => entry.id === button.dataset.mealEdit);
        if (record) openEntry({record, button});
      }
      if (button.dataset.mealDelete) {
        records = records.filter(entry => entry.id !== button.dataset.mealDelete);
        persist();
        render();
        el("mealDiaryStatus").textContent = "음식 기록을 삭제했습니다.";
      }
    });
    el("mealEntryMode").addEventListener("click", event => {
      const button = event.target.closest("[data-entry-mode]");
      if (button) updateMode(button.dataset.entryMode);
    });
    search.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchId++;
      editor.food = null;
      searchResults.replaceChildren();
      el("mealSearchStatus").textContent = "";
      searchTimer = setTimeout(runSearch, 280);
    });
    el("mealFoodSearch").addEventListener("click", () => {
      clearTimeout(searchTimer);
      runSearch();
    });
    search.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        clearTimeout(searchTimer);
        runSearch();
      }
    });
    form.addEventListener("input", updatePreview);
    form.addEventListener("change", event => {
      if (event.target.name === "portion" && event.target.value === "serving") editor.reapplyServing = true;
      updatePreview();
    });
    form.addEventListener("submit", event => {
      event.preventDefault();
      updatePreview();
      if (el("mealEntrySave").disabled) return;
      const entry = currentEntry();
      const original = editor.original;
      entry.id = original?.id || (globalThis.crypto.randomUUID?.() ?? Date.now() + "-" + Math.random());
      if (original) records = records.map(record => record.id === entry.id ? entry : record);
      else records.push(entry);
      date.value = entry.date;
      persist();
      dialog.close();
      if (original || entry.mode !== "cafeteria") render();
      el("mealDiaryStatus").textContent = original ? "음식 기록을 수정했습니다." : "음식을 기록했습니다.";
      el("mealLinkStatus").textContent = `${entry.name}을(를) ${entry.date} ${MEALS[entry.meal]}에 기록했습니다.`;
    });
    el("mealEntryClose").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", event => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right ||
          event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    });
    dialog.addEventListener("close", () => {
      clearTimeout(searchTimer);
      searchId++;
      if (opener?.isConnected) opener.focus();
    });
    // User-provided category standards only: never consult DB serving/package mass.
    if (diary.dataset.servingTable) {
      fetch(diary.dataset.servingTable).then(response => {
        if (!response.ok) throw new Error("serving table");
        return response.json();
      }).then(data => {
        if (data?.version !== 1 || !data.categories) throw new Error("serving categories");
        table = data;
        if (dialog.open) updatePreview();
      }).catch(() => {
        tableFailed = true;
        el("mealDiaryStatus").textContent = "1인분 중량표를 불러오지 못했습니다. DB 기준 단위로 직접 입력해주세요.";
        if (dialog.open) updatePreview();
      });
    }
    render();
    return {
      setContext(next) {
        context = next;
        if (!diary.hidden) render();
      },
      closeEditor() {
        if (dialog.open) dialog.close();
      },
      recordCafeteria(row, button) {
        openEntry({food: cafeteriaFood(row), button});
      },
    };
  }

  globalThis.MealDiary = {mount};
})();
