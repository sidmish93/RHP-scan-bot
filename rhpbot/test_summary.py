import unittest

from rhpbot.summary import _bank_name, _sellers, render, summarize

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
        self.assertNotIn("promoter", fields)
        self.assertIn("Axis Capital Limited", fields["bankers"])
        self.assertEqual(fields["sellers"], "none")
        self.assertIn("Repayment", fields["objects"])

    def test_selling_shareholders(self):
        text = COVER.replace("Not applicable", "aggregating up to ₹10,000.00 lakhs")
        text += " Alpha Capital (the Selling Shareholder) and Beta Ltd (the Selling Shareholder)"
        fields = summarize(text)
        self.assertIn("Alpha Capital", fields["sellers"])
        self.assertNotEqual(fields["ofs"], "none")

    def test_price_clause_and_plain_selling_shareholder(self):
        text = """
        OUR PROMOTER: RELIANCE INDUSTRIES LIMITED
        DETAILS OF THE ISSUE TO THE PUBLIC
        TYPE FRESH ISSUE SIZE OFFER FOR SALE SIZE TOTAL ISSUE SIZE ELIGIBILITY
        Fresh Issue Up to 270,000,000 Equity Shares of face value of ₹10 each for cash at a price of ₹[●] each aggregating up to ₹[●] million
        Not applicable Up to 270,000,000 Equity Shares of face value of ₹10 each aggregating up to ₹[●] million
        The Issue is being made pursuant to Regulation 6(1)
        """
        fields = summarize(text)
        self.assertEqual(fields["fresh"], "up to 270,000,000 equity shares of face value ₹10 each, aggregating up to ₹[●] million")
        self.assertEqual(fields["ofs"], "none")
        self.assertEqual(fields["sellers"], "none")
        self.assertNotIn("promoter", fields)

    def test_seller_without_a_promoter_label_and_a_rupee_amount(self):
        names = _sellers(
            "Alok Kumar Singh Selling Shareholder Up to 63,762,500 Equity Shares of face value of ₹1 each aggregating up to ₹[●] million "
            "Negligible Rahul Anand Promoter Selling Shareholder [●] Equity Shares of face value of ₹10 each aggregating up to ₹1,510.00 million"
        )
        self.assertEqual(
            names,
            [
                "Alok Kumar Singh (up to 63,762,500 shares)",
                "Rahul Anand (₹151 crore)",
            ],
        )

    def test_total_uses_aggregating_to(self):
        text = """
        DETAILS OF THE OFFER TO THE PUBLIC
        TYPE FRESH ISSUE SIZE OFFER FOR SALE SIZE TOTAL OFFER SIZE ELIGIBILITY
        Fresh Issue and Offer for Sale Up to [●] Equity Shares of face value of ₹1 each aggregating up to ₹3,200.00 million
        Up to [●] Equity Shares of face value of ₹1 each aggregating up to ₹2,320.00 million
        Up to [●] Equity Shares of face value of ₹1 each aggregating to ₹5,520.00 million
        The Offer is being made pursuant to Regulation 6(1)
        """
        fields = summarize(text)
        self.assertEqual(fields["fresh"], "₹320 crore")
        self.assertEqual(fields["ofs"], "₹232 crore")
        self.assertEqual(fields["total"], "₹552 crore")

    def test_fund_name_keeps_the_manager_in_brackets(self):
        text = """
        NAME OF THE SELLING SHAREHOLDERS (IN ₹)^
        Ankit Virendra Gupta Promoter Selling Shareholder Up to 6,000,000 Equity Shares bearing face value of ₹2 each aggregating to ₹[●] million Negligible
        Negen Tech Opportunities Angel Fund (represented by its investment manager, Negen Capital Services Private Limited) Investor Selling Shareholder Up to 6,468,315 Equity Shares bearing face value of ₹2 each aggregating to ₹[●] million 13.18#
        Peak XV Partners Investments V (Formerly known as SCI Investments V) Investor Selling Shareholder Up to 17,611,820 Equity Shares of face value of ₹1 each aggregating up to ₹[●] million 6.31
        """
        names = _sellers(text)
        self.assertEqual(
            names,
            [
                "Ankit Virendra Gupta (up to 6,000,000 shares)",
                "Negen Tech Opportunities Angel Fund (represented by its investment manager, Negen Capital Services Private Limited) (up to 6,468,315 shares)",
                "Peak XV Partners Investments V (Formerly known as SCI Investments V) (up to 17,611,820 shares)",
            ],
        )

    def test_selling_shareholder_table_includes_trusts_people_and_investors(self):
        text = """
        NAME OF THE SELLING SHAREHOLDERS TYPE OF SELLING SHAREHOLDER
        Shree Hari Trust Promoter Selling Shareholder Up to 2,700,000 Equity Shares of face value of ₹1 each
        Dhirajkumar Savjibhai Vasoya Promoter Group Selling Shareholder Up to 2,000,000 Equity Shares of face value of ₹1 each
        Samara Capital Markets Holding Limited Investor Selling Shareholder Up to 6,479,063 Equity Shares of face value of ₹1 each
        Kotak Pre-IPO Opportunities Fund Investor Selling Shareholder Up to 1,307,875 Equity Shares of face value of ₹1 each
        NHPEA Sparkle Holding B.V. Investor Selling Shareholder Up to 1,335,178 Equity Shares of face value of ₹1 each
        Each of the Selling Shareholders accepts responsibility
        """
        names = _sellers(text)
        self.assertEqual(
            names,
            [
                "Shree Hari Trust (up to 2,700,000 shares)",
                "Dhirajkumar Savjibhai Vasoya (up to 2,000,000 shares)",
                "Samara Capital Markets Holding Limited (up to 6,479,063 shares)",
                "Kotak Pre-IPO Opportunities Fund (up to 1,307,875 shares)",
                "NHPEA Sparkle Holding B.V. (up to 1,335,178 shares)",
            ],
        )

    def test_placeholder_offer_for_sale_keeps_the_share_count(self):
        fields = summarize(PLACEHOLDER)
        self.assertEqual(fields["fresh"], "none")
        self.assertEqual(
            fields["ofs"],
            "up to 86,418,887 equity shares of face value ₹1 each, aggregating up to ₹[●] million",
        )
        self.assertEqual(fields["total"], fields["ofs"])
        self.assertNotIn("promoter", fields)
        self.assertIn("South Asian Breweries Pte. Ltd", fields["sellers"])
        self.assertIn("Kotak Mahindra Capital Company Limited", fields["bankers"])
        self.assertIn("J.P. Morgan India Private Limited", fields["bankers"])

    def test_a_broken_not_applicable_stays_in_the_fresh_column(self):
        text = """
        DETAILS OF THE OFFER TO THE PUBLIC
        TYPE FRESH ISSUE OFFER FOR SALE TOTAL OFFER SIZE ELIGIBILITY AND RESERVATION
        Offer for Sale Not applicabl e Up to 997,461,45 6 Equity Shares of face value of ₹10 each aggregating up to ₹[●] million Up to 997,461,456 Equity Shares of face value of ₹10 each aggregating up to ₹[●] million
        The Offer is being made pursuant to Regulation 6(1)
        """
        fields = summarize(text)
        self.assertEqual(fields["fresh"], "none")
        self.assertIn("997,461,456", fields["ofs"])
        self.assertEqual(fields["total"], fields["ofs"])

    def test_business_description_is_not_cut_off(self):
        paragraph = (
            "We are an alcoholic beverage company that offers a portfolio of quality internationally "
            "recognized beer brands in India. We have approximately two decades of presence in India "
            "and are part of the Carlsberg Group, which has a 178-year legacy in the global alcobev "
            "industry. We are one of India's fastest growing1 alcobev companies by revenue CAGR from "
            "FY2024 to FY2026 (source: CRISIL Report)."
        )
        fields = summarize("Business overview " + paragraph + " b. Industries served and typical customers")
        self.assertEqual(fields["business"], paragraph.replace("growing1", "growing"))
        self.assertNotIn("...", fields["business"])

    def test_company_description_can_start_with_we_own(self):
        text = (
            "Summary of the primary business We own and operate Burma Burma, India's largest specialty "
            "Burmese restaurant chain. As of July 31, 2026, we operate 22 restaurants across nine cities. "
            "a. Business Overview – Products and Services Our offerings include dine-in and delivery."
        )
        fields = summarize(text)
        self.assertTrue(fields["business"].startswith("We own and operate Burma Burma"))
        self.assertIn("22 restaurants", fields["business"])
        self.assertNotIn("offerings include", fields["business"])

    def test_business_comes_from_the_primary_summary_not_a_clipped_later_line(self):
        later = "Business Overview - Products and Services " + ("Digital connectivity services. " * 80)
        text = (
            "Summary of the primary business We are a technology platform, built on proprietary digital "
            "technology and pan-India digital connectivity. Since our inception, we have played a pivotal "
            "role in democratising access to digital connectivity and digital services in India. "
            "In this context: a) Our Company had 12,477 employees. "
            + later
            + "We are engaged in mobile networks."
        )
        fields = summarize(text)
        self.assertTrue(fields["business"].startswith("We are a technology platform"))
        self.assertIn("democratising access", fields["business"])
        self.assertNotIn("employees", fields["business"])
        self.assertNotIn("engaged", fields["business"])

    def test_the_summary_paragraph_stands_without_the_products_subsection(self):
        text = (
            "Summary of the primary business We are a financial technology company focused on digital gifting. "
            "a. Business Overview - Products and services We act as a program manager for prepaid cards and "
            "offer consumer spend management through our SpendPro platform. "
            "b. Industries served and typical customers Banks and merchants."
        )
        fields = summarize(text)
        self.assertEqual(
            fields["business"],
            "We are a financial technology company focused on digital gifting.",
        )

    def test_lettered_overview_heading_is_not_the_description(self):
        text = (
            "Summary of the primary business a. Business overview – products and services "
            "We are an alcoholic beverage company that offers beer brands in India. "
            "b. Industries served and typical customers Restaurants."
        )
        fields = summarize(text)
        self.assertEqual(
            fields["business"],
            "We are an alcoholic beverage company that offers beer brands in India.",
        )
        labelled = (
            "Summary of the primary business a. Business Overview - products or services offered by our Company "
            "We are the largest beverage company operating in India. "
            "b. Industries served Retailers."
        )
        self.assertTrue(summarize(labelled)["business"].startswith("We are the largest beverage company"))
        sourced = (
            "Summary of the primary business a. Business Overview - Products and Services "
            "As per the CRISIL Report, we are a manufacturer of polymer compounds. "
            "b. Industries served Cable makers."
        )
        self.assertTrue(summarize(sourced)["business"].startswith("As per the CRISIL Report"))

    def test_description_can_open_with_the_company_name(self):
        text = (
            "Summary of the primary business GAMP Services Limited is a compliance and validation company "
            "providing validation and qualification solutions to customers in regulated industries. "
            "a. Business overview – products and services We operate on a B2B business model."
        )
        fields = summarize(text)
        self.assertTrue(fields["business"].startswith("GAMP Services Limited is a compliance"))
        self.assertNotIn("B2B", fields["business"])

    def test_an_unlettered_products_heading_ends_the_summary(self):
        text = (
            "Summary of the primary business Our Business Model We are a technology-led manufacturing platform. "
            "Business overview – products and services We operate through two segments. "
            "1. Our Manufacturing Business offers capital goods."
        )
        fields = summarize(text)
        self.assertEqual(fields["business"], "We are a technology-led manufacturing platform.")

    def test_issue_table_is_read_when_the_banner_comes_first(self):
        fields = summarize("IN THE NATURE OF AN ABRIDGED PROSPECTUS " + ("cover " * 40) + COVER)
        self.assertEqual(fields["fresh"], "₹2,500 crore")
        self.assertEqual(fields["ofs"], "none")

    def test_bank_name_drops_the_email_header(self):
        self.assertEqual(_bank_name("AND E- MAIL SBI Capital Markets Limited"), "SBI Capital Markets Limited")
        self.assertEqual(
            _bank_name("Id Smart Horizon Capital Advisors Private Limited"),
            "Smart Horizon Capital Advisors Private Limited",
        )

    def test_message_includes_the_sebi_page(self):
        body = render("DRHP", "Acme Limited", "19 Nov 2026", {"fresh": "₹100 crore"}, "https://sebi.example/a", "")
        self.assertIn("DRHP · Acme Limited", body)
        self.assertIn("https://sebi.example/a", body)


if __name__ == "__main__":
    unittest.main()
