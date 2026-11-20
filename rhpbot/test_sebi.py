import unittest

from rhpbot.sebi import kind_of, parse_listing

HTML = """
<tr role='row' class='odd'>
  <td>Nov 19, 2026</td>
  <td><a href="https://www.sebi.gov.in/filings/public-issues/nov-2026/chartered-speed-limited-addendum-to-the-drhp_1.html" title="Addendum">Chartered Speed Limited_Addendum to the DRHP</a></td>
</tr>
<tr>
  <td>Nov 17, 2026</td>
  <td><a href="https://www.sebi.gov.in/filings/public-issues/nov-2026/il-jin_2.html">IL JIN ELECTRONICS (INDIA) LIMITED - DRHP</a>
  <a href="https://www.sebi.gov.in/sebi_data/commondocs/nov-2026/IL_p.pdf">Draft Abridged Prospectus</a></td>
</tr>
<tr>
  <td>Nov 14, 2026</td>
  <td><a href="https://www.sebi.gov.in/filings/public-issues/nov-2026/rediff_3.html">Rediff com India Limited - UDRHP-I</a>
</tr>
<tr>
  <td>Nov 14, 2026</td>
  <td><a href="https://www.sebi.gov.in/filings/public-issues/nov-2026/mcl_4.html">Mahanadi Coalfields Limited - RHP</a></td>
</tr>
"""


class ListingTests(unittest.TestCase):
    def test_keeps_prospectuses_and_drops_addenda(self):
        items = parse_listing(HTML)
        kinds = [(item.company, item.kind, item.filed) for item in items]
        self.assertEqual(
            kinds,
            [
                ("IL JIN ELECTRONICS (INDIA) LIMITED", "DRHP", "17 Nov 2026"),
                ("Rediff com India Limited", "UDRHP", "14 Nov 2026"),
                ("Mahanadi Coalfields Limited", "RHP", "14 Nov 2026"),
            ],
        )
        self.assertTrue(items[0].abridged.endswith("_p.pdf"))
        self.assertIsNone(kind_of("SFC Environmental Technologies Ltd - Addendum to RHP"))


if __name__ == "__main__":
    unittest.main()
