import unittest
from export_allergy_web import suppress_partial_cutlet_shellfish as suppress


class AllergyPolicy(unittest.TestCase):
    def test_only_partial_shellfish_cutlet_evidence_suppressed(self):
        part={'name':'고구마치즈돈까스','name_indications':[]}
        stat={'labeled_record_count':1,'total_record_count':2}
        self.assertTrue(suppress(18,stat,part))
        self.assertFalse(suppress(2,stat,part))
        self.assertFalse(suppress(18,{'labeled_record_count':1,'total_record_count':1},part))

    def test_shellfish_name_and_accompanying_dish_remain(self):
        stat={'labeled_record_count':1,'total_record_count':2}
        cutlet={'name':'고구마치즈돈까스','name_indications':[]}
        side={'name':'바지락미역국','name_indications':[{'number':18}]}
        # Synthetic combination verifies that correcting the cutlet cannot erase the side.
        self.assertEqual([p['name'] for p in [cutlet,side] if not suppress(18,stat,p)],['바지락미역국'])
        self.assertFalse(suppress(18,stat,{'name':'굴돈가스','name_indications':[{'number':18}]}))

    def test_other_partial_evidence_not_removed(self):
        stat={'labeled_record_count':1,'total_record_count':9}
        self.assertFalse(suppress(18,stat,{'name':'된장찌개','name_indications':[]}))
        self.assertFalse(suppress(18,stat,{'name':'돈가스소스','name_indications':[]}))


if __name__=='__main__':unittest.main()
