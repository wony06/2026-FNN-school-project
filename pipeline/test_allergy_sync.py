"""Coverage/source-boundary regressions for automatic allergy exports."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from sync_allergy_data import ROOT, source_fingerprints, validate_coverage
from match_hyu_neis import run as match_menus
from classify_hyu_allergens import run as classify_menus


class AllergySynchronizationTest(unittest.TestCase):
    def test_current_menus_are_all_connected_once(self):
        rows = json.loads((ROOT / 'web/site_data.json').read_text(encoding='utf-8'))
        export = json.loads((ROOT / 'web/allergy-data.json').read_text(encoding='utf-8'))
        validate_coverage(rows, export)
        self.assertEqual(len(rows), 484)
        self.assertEqual(sum('2026-11-09' <= m['key'][0] <= '2026-11-13' for m in export['meals']), 35)
        self.assertEqual(sum(m['state'] == 'choice_withheld' for m in export['meals']), 50)

    def test_missing_and_duplicate_exports_fail_instead_of_passing_silently(self):
        row = {'date': '2026-11-11', 'shop': '204', 'category': '일품', 'main': '왕돈까스'}
        entry = {'key': list(row.values()), 'allergens': [], 'state': 'estimated_unverified', 'actualIngredientsConfirmed': False}
        validate_coverage([row], {'meals': [entry]})
        with self.assertRaises(ValueError): validate_coverage([row], {'meals': []})
        with self.assertRaises(ValueError): validate_coverage([row], {'meals': [entry, entry]})
        with self.assertRaises(ValueError): validate_coverage([row, row], {'meals': [entry]})

    def test_only_official_menu_text_changes_invalidate_evidence(self):
        row = {'date': '2026-12-01', 'shop': '204', 'category': '정식', 'main': '두부국'}
        parsed = [{**row, 'sides': ['배추김치'], 'cat_idx': 0, 'img': 'old.jpg'}]
        source = {'days': [{'date': row['date'], 's204': {'items': [{'category': row['category'], 'name': '두부국 배추김치', 'desc': '-', 'img': 'old.jpg'}]}}]}
        initial = source_fingerprints([row], parsed, source)
        changed_row = {**row, 'photo': 'new.jpg', 'kcal': 9999, 'components': ['새우'], 'itemDetails': [{'display': '가정한 새우'}]}
        changed_source = copy.deepcopy(source)
        changed_source['days'][0]['s204']['items'][0]['img'] = 'new.jpg'
        self.assertEqual(initial, source_fingerprints([changed_row], parsed, changed_source))
        changed_source['days'][0]['s204']['items'][0]['name'] += ' 새우'
        self.assertNotEqual(initial, source_fingerprints([row], parsed, changed_source))

    def test_a_single_new_meal_uses_existing_parser_and_ignores_assumed_components(self):
        rows = json.loads((ROOT / 'web/site_data.json').read_text(encoding='utf-8'))
        row = copy.deepcopy(next(r for r in rows if r['date'] == '2026-11-11' and r['main'] == '왕돈까스'))
        row['components'] = ['새우', '땅콩', '가정한 우유소스']
        with tempfile.TemporaryDirectory(prefix='_test-', dir=ROOT / 'pipeline/hyu_allergy_incremental') as d:
            out = Path(d)
            match_menus(meals=[row], out_dir=out / 'matching', verbose=False)
            classify_menus(input_dir=out / 'matching', out_dir=out / 'analysis', verbose=False)
            meals = json.loads((out / 'analysis/meal_estimates.json').read_text(encoding='utf-8'))
            self.assertEqual(len(meals), 1)
            self.assertEqual(len(meals[0]['allergens']), 19)
            names = {c['name'] for c in meals[0]['components']}
            self.assertIn('요구르트', names)
            self.assertNotIn('가정한 우유소스', names)
            self.assertNotIn('새우', names)
            self.assertNotIn('땅콩', names)


if __name__ == '__main__':
    unittest.main()
