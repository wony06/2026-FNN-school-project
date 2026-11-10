import unittest
from build_month import expand_side
from exchange_unit import compute_kimchi_pair

class KimchiPhotoPairsTest(unittest.TestCase):
    def test_november_photo_pairs_keep_total_weight(self):
        for day,expected in [('2026-11-09',['깍두기','열무김치']),('2026-11-10',['배추김치','열무김치'])]:
            with self.subTest(day=day):
                parts=expand_side('김치2종',shop='401',date=day)
                self.assertEqual([n for n,_,_ in parts],expected)
                self.assertEqual([w for _,w,_ in parts],[35,35])
                self.assertIn('대체 추정',parts[0][2])
                pair=compute_kimchi_pair(day,70)
                self.assertTrue(pair['matched'])
                self.assertIn('깍두기' if day.endswith('09') else '배추',pair['matched_ingredients'][0])
                self.assertIn('열무',pair['matched_ingredients'][1])
                self.assertGreater(pair['units']['채소군'],0)

    def test_existing_date_defaults_are_preserved(self):
        pair=compute_kimchi_pair('2026-11-05',70)
        self.assertEqual(pair['matched_ingredients'],['김치, 배추 김치','김치, 깍두기'])
        self.assertIsNone(compute_kimchi_pair('2026-11-11',70))

if __name__=='__main__':unittest.main()
