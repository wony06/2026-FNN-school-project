import unittest
from build_neis_reference import aggregate, make_records, normalize_name, parse_dishes


class ReferenceTests(unittest.TestCase):
    def test_aliases_preserve_ingredients(self):
        self.assertEqual(normalize_name(' 돈까스 '), normalize_name('돈가스'))
        self.assertEqual(normalize_name('치즈 돈까스'), normalize_name('치즈돈가스'))
        self.assertNotEqual(normalize_name('치즈돈까스'), normalize_name('돈까스'))
        self.assertNotEqual(normalize_name('생선까스'), normalize_name('돈까스'))

    def test_labels_and_quantities(self):
        rows=list(parse_dishes('칼슘밥<br/>돈까스(100g) (1.2.5.6.)<BR>닭고기/소스 (5,6,15)'))
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[0]['label_status'],'미표기')
        self.assertEqual(rows[1]['original_menu_name'],'돈까스(100g)')
        self.assertEqual(rows[1]['allergy_numbers'],[1,2,5,6])
        self.assertEqual(rows[2]['original_menu_name'],'닭고기/소스')
        self.assertEqual(rows[2]['allergy_numbers'],[5,6,15])

    def test_unrecognized_label_needs_review(self):
        row=list(parse_dishes('수제요리 (1.20)'))[0]
        self.assertEqual(row['label_status'],'검토필요')
        self.assertEqual(row['allergy_numbers'],[])
        self.assertIn('(1.20)',row['original_menu_name'])

    def test_raw_source_survives_normalization(self):
        row=list(parse_dishes('치즈  돈까스 （１．２．６）'))[0]
        self.assertEqual(row['source_text'],'치즈  돈까스 （１．２．６）')
        self.assertEqual(row['original_menu_name'],'치즈  돈까스')
        self.assertEqual(row['normalized_menu_name'],'치즈돈가스')
        self.assertEqual(row['allergy_numbers'],[1,2,6])

    def test_school_count_and_record_count_differ(self):
        rows=[]
        for i,(school,text) in enumerate([('A','돈까스 (1.6)'),('A','돈가스 (1.6)'),('B','돈까스 (6)'),('C','돈까스')]):
            rows.append(dict(next(parse_dishes(text)),record_id=str(i),school_code=school,school_name=school))
        result=aggregate(rows)[0]
        self.assertEqual(result['record_count'],4)
        self.assertEqual(result['school_count'],3)
        self.assertEqual(result['unlabeled_record_count'],1)
        stats={s['number']:s for s in result['allergens']}
        self.assertEqual(stats[1]['labeled_school_count'],1)
        self.assertEqual(stats[1]['labeled_record_count'],2)
        self.assertEqual(stats[6]['labeled_school_count'],2)
        self.assertEqual(stats[6]['total_record_count'],4)

    def test_api_duplicate_removed_but_distinct_dates_retained(self):
        meal={'ATPT_OFCDC_SC_CODE':'B10','SD_SCHUL_CODE':'A','SCHUL_NM':'학교A',
              'MLSV_YMD':'20260901','MMEAL_SC_CODE':'2','MMEAL_SC_NM':'중식',
              'DDISH_NM':'밥<br/>돈까스 (1.6)','_fetched_at':'test'}
        rows,duplicates,count=make_records([meal,dict(meal),dict(meal,MLSV_YMD='20260902')])
        self.assertEqual((len(rows),duplicates,count),(4,1,2))


if __name__=='__main__':
    unittest.main()
