import unittest

from rhpbot.summary import _bank_name, render, summarize

COVER = """
NAME OF OUR PROMOTER: AMBER ENTERPRISES INDIA LIMITED
DETAILS OF ISSUE TO THE PUBLIC
TYPE FRESH ISSUE SIZE OFFER FOR SALE SIZE TOTAL ISSUE SIZE ELIGIBILITY
Fresh Issue Up to [●] Equity Shares aggregating up to ₹2,50,000.00 lakhs
Not applicable Up to [●] Equity Shares aggregating up to ₹2,50,000.00 lakhs
The Issue is being made pursuant to Regulation 6(2)
BOOK RUNNING LEAD MANAGERS
NAME OF BRLM AND LOGO CONTACT PERSON E-MAIL AND TELEPHONE
Motilal Oswal Investment Advisors Limited Ronak Shah E-mail: iljin.ipo@motilaloswal.com
Axis Capital Limited Simran Gadh E-mail: iljin.ipo@axiscap.in
Jefferies India Private Limited Nidhi Rana E-mail: ILJIN.IPO@jefferies.com
REGISTRAR TO THE ISSUE
Pre-IPO Placement of Specified Securities, aggregating up to ₹50,000.00 lakhs
IN THE NATURE OF DRAFT ABRIDGED PROSPECTUS
We are one of the leading electronics manufacturers in India.
Objects of the Issue
1. Repayment and prepayment of certain outstanding borrowings 1,63,600.00
2. Purchase of certain plant and machinery 18,900.00
Total Net Proceeds
"""

PLACEHOLDER = """
THE PROMOTERS OF OUR COMPANY ARE CARLSBERG A/S AND SOUTH ASIAN BREWERIES PTE. LTD
DETAILS OF THE OFFER TO THE PUBLIC
TYPE FRESH ISSUE SIZE OFFER FOR SALE SIZE TOTAL OFFER SIZE ELIGIBILITY AND RESERVATION
Offer for Sale Not applicable Offer for Sale of up to 86,418,887 Equity Shares of face value of ₹1 each aggregating up to ₹[●] million Up to 86,418,887 Equity Shares of face value of ₹1 each aggregating up to ₹ [●] million
The Offer is being made pursuant to Regulation 6(1)
DETAILS OF THE OFFER FOR SALE
South Asian Breweries Pte. Ltd Promoter Selling Shareholder Up to 86,418,887 Equity Shares
BOOK RUNNING LEAD MANAGERS
Kotak Mahindra Capital Company Limited Ganesh Rane E-mail: carlsberg.ipo@kotak.com
Citigroup Global Markets India Private Limited Sivamsa Pingali E-mail: carlsbergindia.ipo@citi.com
J.P. Morgan India Private Limited Darshil Mehta E-mail: carlsberg_India_IPO@jpmorgan.com
REGISTRAR TO THE OFFER
"""


class SummaryTests(unittest.TestCase):
    def test_cover_fields(self):
        fields = summarize(COVER)
        self.assertEqual(fields["fresh"], "₹2,500 crore")
        self.assertEqual(fields["ofs"], "none")
        self.assertEqual(fields["total"], "₹2,500 crore")
        self.assertEqual(fields["pre_ipo"], "up to ₹500 crore")
        self.assertIn("AMBER ENTERPRISES", fields["promoter"])
        self.assertIn("Axis Capital Limited", fields["bankers"])
        self.assertEqual(fields["sellers"], "none")
        self.assertIn("Repayment", fields["objects"])

    def test_selling_shareholders(self):
        text = COVER.replace("Not applicable", "aggregating up to ₹10,000.00 lakhs")
        text += " Alpha Capital (the Selling Shareholder) and Beta Ltd (the Selling Shareholder)"
        fields = summarize(text)
        self.assertIn("Alpha Capital", fields["sellers"])
        self.assertNotEqual(fields["ofs"], "none")

    def test_placeholder_offer_for_sale_keeps_the_share_count(self):
        fields = summarize(PLACEHOLDER)
        self.assertEqual(fields["fresh"], "none")
        self.assertEqual(
            fields["ofs"],
            "up to 86,418,887 equity shares of face value ₹1 each, aggregating up to ₹[●] million",
        )
        self.assertEqual(fields["total"], fields["ofs"])
        self.assertIn("CARLSBERG A/S", fields["promoter"])
        self.assertIn("South Asian Breweries Pte. Ltd", fields["sellers"])
        self.assertIn("Kotak Mahindra Capital Company Limited", fields["bankers"])
        self.assertIn("J.P. Morgan India Private Limited", fields["bankers"])

    def test_bank_name_drops_the_email_header(self):
        self.assertEqual(_bank_name("AND E- MAIL SBI Capital Markets Limited"), "SBI Capital Markets Limited")

    def test_message_includes_the_sebi_page(self):
        body = render("DRHP", "Acme Limited", "19 Nov 2026", {"fresh": "₹100 crore"}, "https://sebi.example/a", "")
        self.assertIn("DRHP · Acme Limited", body)
        self.assertIn("https://sebi.example/a", body)


if __name__ == "__main__":
    unittest.main()
