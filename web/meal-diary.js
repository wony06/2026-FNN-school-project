(function () {
  "use strict";

  const MEALS = {breakfast: "아침", lunch: "점심", dinner: "저녁", snack: "간식"};
  const KINDS = {cooked: "조리식품", processed: "가공식품", ingredient: "식품 원재료·성분표"};
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

  function servingGrams(food, table) {
    const positive = value => Number.isFinite(value) && value > 0 ? value : null;
    const exact = positive(table?.foods?.[food.id]);
    if (exact !== null) return exact;
    const reviewedType = table?.foodTypes?.[food.id];
    return typeof reviewedType === "string" ? positive(table?.types?.[reviewedType]) : null;
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

  function scale(food, amount) {
    const factor = amount === null ? 1 : amount / food.grams;
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
    const gramBasis = /^(\d+(?:\.\d+)?)\s*g$/i.exec(basis);
    return {
      id, name, source, detail, foodType, basis, kind: id.split(":")[0],
      grams: gramBasis && Number(gramBasis[1]) > 0 ? Number(gramBasis[1]) : null,
      nutrients: Object.fromEntries(NUTRIENTS.map((key, i) => [key, valueOrNull(values[i])])),
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
    const grams = el("mealEntryGrams");
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
      const amount = entry.amount === null ? "중량 미확인" : fmt(entry.amount) + " g";
      if (entry.mode === "cafeteria") {
        return (entry.portion === "serving" ? "학식 추정 1인분 · " : "학식 g 환산 · ") + amount;
      }
      return (entry.portion === "serving" ? "기본 1인분 · " : "") + amount;
    }

    function sumLabel(amount, unit) {
      if (amount.partial && !amount.available) return "미확인";
      return `${amount.partial ? "확인된 합계 " : ""}${fmt(amount.known)} ${unit}`;
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

    function renderSummary(entries) {
      const total = totals(entries);
      const targets = diaryTargets(context);
      const energy = total.kcal;
      const goal = targets?.kcal;
      let energyNote = "기본 정보와 영양 목표를 입력하면 목표를 확인할 수 있어요.";
      if (goal && energy.partial) energyNote = "열량 정보가 부족해 남은 목표량이나 초과량을 확정할 수 없어요.";
      else if (goal) {
        const left = goal - energy.known;
        energyNote = left < 0 ? `${fmt(-left)} kcal 초과` : `목표까지 ${fmt(left)} kcal 남음`;
      }
      el("mealEnergySummary").innerHTML = `
        <p class="meal-kicker">하루 총섭취 열량</p>
        <div class="meal-energy-number"><strong>${energy.partial && !energy.available ? "—" : fmt(energy.known)}</strong> kcal <span>/ ${goal ? fmt(goal) + " kcal 목표" : "목표 미설정"}</span></div>
        ${goal ? bar(energy, 0, goal, false) : ""}
        <p>${energy.partial ? "확인된 열량 합계입니다. " : ""}${energyNote}</p>
        ${targets?.weightLoss ? '<p class="meal-muted">기존 체중감량 설정의 조정 열량입니다. 낮은 목표 열량은 적절한지 확인해주세요.</p>' : ""}`;
      const cards = Object.entries(MACROS).map(([key, macro]) => {
        const amount = total[key];
        const range = targets?.ranges[key];
        const ratio = !energy.partial && !amount.partial && energy.known > 0
          ? fmt(amount.known * macro.factor / energy.known * 100) + "%" : "—";
        let status = "목표 범위 미설정";
        if (range) {
          const [lower, upper] = range;
          if (amount.known > upper) status = `하한까지 0 g · 상한 ${fmt(amount.known - upper)} g 초과`;
          else if (amount.partial) status = "자료 부족으로 범위 판정 보류";
          else if (amount.known < lower) status = `하한까지 ${fmt(lower - amount.known)} g 남음 · 상한 이내`;
          else status = "적정 범위 내 · 하한까지 0 g · 상한 이내";
        }
        return `<article class="meal-macro"><h4>${macro.name}</h4>
          <p class="meal-macro-value">${amount.partial ? "확인된 합계 " : ""}<strong>${amount.partial && !amount.available ? "—" : fmt(amount.known)}</strong> g</p>
          <p>하루 참고 범위 ${range ? fmt(range[0]) + "–" + fmt(range[1]) + " g" : "—"}</p>
          ${range ? bar(amount, ...range) : ""}
          <p>기록 열량 대비 ${ratio}</p><p class="meal-macro-status">${status}</p></article>`;
      });
      el("mealMacroSummary").innerHTML = cards.join("");
      const high = el("mealProteinTarget");
      high.hidden = targets?.highProtein == null;
      if (!high.hidden) {
        const above = targets.highProtein > targets.ranges.protein[1];
        const amount = total.protein;
        const status = amount.partial ? "결측 자료가 있어 남은 양은 확인할 수 없어요." :
          amount.known >= targets.highProtein ? "하루 고단백 목표에 도달했어요." :
          `고단백 목표까지 ${fmt(targets.highProtein - amount.known)} g 남았어요.`;
        high.textContent = `하루 고단백 목표 ${fmt(targets.highProtein)} g (체중 × 1.2 g/kg). ${status} ${above ? "이 목표는 일반 단백질 적정 범위 상한(에너지의 20%)보다 높습니다. " : ""}일반 단백질 적정 범위와 별개의 서비스 목표입니다.`;
      }
    }

    function renderMeals(entries) {
      el("mealDiaryMeals").innerHTML = Object.entries(MEALS).map(([key, label]) => {
        const group = entries.filter(record => record.meal === key);
        const total = totals(group);
        const rows = group.map(record => `<li class="meal-record">
          <div><strong>${escape(record.name)}</strong><p>${escape(amountLabel(record))} · ${record.nutrients.kcal === null ? "열량 미확인" : fmt(record.nutrients.kcal) + " kcal"}</p>
          <p>${escape(record.mode === "manual" ? "직접 기록" : record.base?.source)}${record.incomplete?.length ? " · 영양정보 일부 미확인" : ""}</p>
          ${record.base?.excluded ? '<p>알레르기 근거로 추천에서 제외된 메뉴</p>' : ""}</div>
          <div class="meal-record-actions"><button type="button" data-meal-edit="${escape(record.id)}" aria-label="${escape(record.name)} 수정">수정</button>
          <button type="button" data-meal-delete="${escape(record.id)}" aria-label="${escape(record.name)} 삭제">삭제</button></div></li>`).join("");
        return `<section class="meal-card meal-slot"><div class="meal-slot-head"><h3>${label}</h3><button type="button" class="meal-outline" data-meal-add="${key}">+ 음식 추가</button></div>
          ${group.length ? `<ul class="meal-records">${rows}</ul><p class="meal-slot-total">${sumLabel(total.kcal, "kcal")} · 탄 ${sumLabel(total.carb, "g")} · 단 ${sumLabel(total.protein, "g")} · 지 ${sumLabel(total.fat, "g")}</p>` :
          '<p class="meal-muted">아직 기록한 음식이 없습니다.</p>'}</section>`;
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

    function activeServing() {
      if (!editor.food) return null;
      if (editor.mode === "cafeteria") return editor.food.grams;
      if (editor.original?.base?.id === editor.food.id && editor.original.portion === "serving") {
        return editor.original.amount;
      }
      return servingGrams(editor.food, table);
    }

    function currentEntry() {
      const mode = editor.mode;
      const base = editor.food;
      const portion = form.elements.portion.value;
      let name, amount, nutrients;
      if (mode === "manual") {
        name = el("mealManualName").value.trim();
        if (!name) return null;
        nutrients = Object.fromEntries(Object.keys(MACROS).map(key => [key, readNumber(el("mealManual-" + key))]));
        if (Object.values(nutrients).some(value => value === null)) return null;
        nutrients.kcal = Object.entries(MACROS).reduce((sum, [key, macro]) => sum + nutrients[key] * macro.factor, 0);
        if (!Number.isFinite(nutrients.kcal)) return null;
        amount = null;
      } else {
        if (!base || (mode === "database" && !base.grams)) return null;
        name = base.name;
        amount = portion === "serving" ? activeServing() : readNumber(grams);
        if (portion === "grams" && (!base.grams || !amount)) return null;
        if (mode === "database" && !amount) return null;
        nutrients = scale(base, amount);
        if (!nutrients) return null;
      }
      return {
        date: entryDate.value, meal: entryMeal.value, mode, name, amount,
        portion: mode === "manual" ? null : portion,
        nutrients, base: mode === "manual" ? null : base,
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
      const serving = activeServing();
      const servingOption = el("mealPortionServing");
      const gramOption = el("mealPortionGrams");
      const servingAvailable = mode === "cafeteria" || Boolean(serving);
      servingOption.closest("label").hidden = !servingAvailable;
      gramOption.closest("label").hidden = !food?.grams;
      el("mealEntryPortions").hidden = mode === "manual" || !food;
      el("mealServingLabel").textContent = mode === "cafeteria"
        ? `기존 추정 1인분${serving ? " · " + fmt(serving) + " g" : " · 중량 미확인"}`
        : `기본 1인분${serving ? " · " + fmt(serving) + " g" : ""}`;
      if (servingOption.checked && !servingAvailable) gramOption.checked = true;
      el("mealGramsField").hidden = mode === "manual" || !food?.grams || !gramOption.checked;
      el("mealServingHint").textContent = mode === "database" && food && !serving
        ? "연결된 1인분 중량이 없어 실제 섭취량을 g으로 입력해야 합니다." :
        mode === "cafeteria" && food?.grams ? "g 입력 시 한 끼 전체 추정 영양값을 중량에 비례해 환산합니다." : "";
      el("mealEntrySource").textContent = mode !== "manual" && food
        ? [food.name, food.source, food.detail, food.basis].filter(Boolean).join(" · ") : "";
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
      el("mealPortionGrams").checked = !el("mealPortionServing").checked;
      grams.value = record?.amount ?? "";
      updateMode(record?.mode || (food ? "cafeteria" : "database"));
      dialog.showModal();
    }

    function renderSearch({groups, counts, error}) {
      searchResults.replaceChildren();
      el("mealSearchStatus").textContent = error || (Object.values(counts).some(Boolean)
        ? "기준량과 출처를 확인하고 정확한 항목을 선택해주세요. 유형별 최대 20건을 표시합니다."
        : "검색 결과가 없습니다. 다른 이름으로 검색하거나 직접 입력해주세요.");
      if (error) return;
      for (const [kind, rows] of Object.entries(groups)) {
        if (!rows.length) continue;
        const heading = document.createElement("h4");
        heading.textContent = `${KINDS[kind]} · ${fmt(counts[kind])}건`;
        searchResults.append(heading);
        for (const row of rows) {
          const food = databaseFood(row);
          const button = document.createElement("button");
          button.type = "button";
          button.className = "meal-search-result";
          button.disabled = !food.grams;
          button.innerHTML = `<strong>${escape(food.name)}</strong><small>${escape([food.source, food.detail, food.basis, food.id.split(":").slice(1).join(":")].filter(Boolean).join(" · "))}${food.grams ? "" : " · g 환산 불가"}</small>`;
          button.addEventListener("click", () => {
            editor.food = food;
            grams.value = "";
            el("mealPortionServing").checked = Boolean(servingGrams(food, table));
            el("mealPortionGrams").checked = !el("mealPortionServing").checked;
            searchResults.replaceChildren();
            el("mealSearchStatus").textContent = "";
            updatePreview();
            (el("mealPortionServing").checked ? el("mealPortionServing") : grams).focus();
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
          worker = new Worker("./meal-food-search.js?v=1");
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
    form.addEventListener("change", updatePreview);
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
    // Optional: set data-serving-table on the diary panel when the team table is available.
    if (diary.dataset.servingTable) {
      fetch(diary.dataset.servingTable).then(response => {
        if (!response.ok) throw new Error("serving table");
        return response.json();
      }).then(data => {
        table = data;
        if (dialog.open) updatePreview();
      }).catch(() => {
        el("mealDiaryStatus").textContent = "1인분 중량표를 불러오지 못했습니다. g으로 입력해주세요.";
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
