# OnWebApp Automation Library: 100+ Commercial Use Cases

This document serves as the comprehensive catalog of automation scenarios supported by OnWebApp. It is designed for use in sales enablement, marketing landing pages, template libraries, and investor presentations.

**Product Scope**: Business Automation, API Integration, Web Crawling, Workflow Orchestration.

---

## 1. Finance & Billing
*Streamline cash flow, reduce manual data entry, and ensure financial accuracy.*

1.  **Automated Invoice Reconciliation**
    *   **Problem**: Matching Stripe payments to Xero invoices manually is slow and error-prone.
    *   **Workflow**: Trigger: Stripe Payment Received -> Find Xero Invoice -> Mark as Paid -> Upload Receipt to Drive.
    *   **Systems**: Stripe, Xero/QuickBooks, Google Drive.
    *   **Value**: Saves 10+ hours/month, ensures 100% accuracy.

2.  **The "Late Payment Chaser"**
    *   **Problem**: Unpaid invoices hurt cash flow; manual follow-ups are awkward.
    *   **Workflow**: Daily Schedule -> Check ERP for Overdue > 7 Days -> Send Polite Email -> If > 30 Days, Alert CFO.
    *   **Systems**: ERP (Netsuite/Sage), Email, Slack.
    *   **Value**: Reduces Days Sales Outstanding (DSO) by 20%.

3.  **Expense Receipt Automation**
    *   **Problem**: Lost receipts and delayed expense reports.
    *   **Workflow**: Email with Attachment -> OCR Scan -> Create Expense in Concur -> Match to Credit Card Feed.
    *   **Systems**: Email, OCR, Concur/Expensify.
    *   **Value**: Real-time expense tracking, faster reimbursement.

4.  **Daily Sales Metrics Dashboard**
    *   **Problem**: Executives lack a unified view of daily revenue.
    *   **Workflow**: 6 PM Daily -> Fetch Shopify + Stripe + PayPal Totals -> Sum Revenue -> Post to Slack Executive Channel.
    *   **Systems**: Shopify, Stripe, Slack.
    *   **Value**: Immediate visibility into business health.

5.  **VAT/Tax Rate Auto-Updater**
    *   **Problem**: Global tax rates change, leading to compliance risks.
    *   **Workflow**: Weekly Crawl of Govt Tax Sites -> Compare with ERP Tax Table -> Alert if Mismatch.
    *   **Systems**: OnWebApp Crawler, ERP.
    *   **Value**: Prevents costly compliance errors.

6.  **Vendor Onboarding Verification**
    *   **Problem**: Onboarding new vendors requires manual background checks.
    *   **Workflow**: Vendor Form Submit -> Crawl Business Registry -> Check Sanctions List API -> Update ERP Vendor Status.
    *   **Systems**: Typeform, Government APIs, ERP.
    *   **Value**: Automates due diligence and risk management.

7.  **Recurring Subscription Failure Recovery**
    *   **Problem**: Failed credit card charges lead to involuntary churn.
    *   **Workflow**: Stripe "Invoice Payment Failed" -> Wait 2 Days -> Send "Update Card" Email -> If Fail again, Create Support Ticket.
    *   **Systems**: Stripe, Email, Zendesk.
    *   **Value**: Recovers 5-10% of lost revenue automatically.

8.  **Budget Variance Alert**
    *   **Problem**: Teams overspend before Finance notices.
    *   **Workflow**: Weekly -> Fetch Xero Actuals -> Compare to Google Sheet Budget -> If Variance > 10%, Slack Dept Head.
    *   **Systems**: Xero, Google Sheets, Slack.
    *   **Value**: Proactive cost control.

9.  **Crypto Payment Confirmation**
    *   **Problem**: Crypto payments are manual and disconnected from main order systems.
    *   **Workflow**: Watch Blockchain Address -> Transaction Confirmed -> Update E-commerce Order Status -> Email Customer.
    *   **Systems**: Blockchain API, Shopify/WooCommerce.
    *   **Value**: Enables seamless alternative payment acceptance.

10. **Sales Commission Calculator**
    *   **Problem**: Sales reps distrust manual spreadsheet calculations.
    *   **Workflow**: End of Month -> Fetch "Closed Won" Deals -> Apply Commission Logic -> Add to Payroll Sheet -> Email Rep Statement.
    *   **Systems**: Salesforce, Google Sheets, Gmail.
    *   **Value**: Increases trust and saves 2 days of Finance time.

11. **Purchase Order (PO) Approval Routing**
    *   **Problem**: POs get stuck in email chains.
    *   **Workflow**: PO Request Form -> If < $5k Auto-Approve -> If > $5k Email Manager -> Manager Click "Approve" -> Create PO in ERP.
    *   **Systems**: Web Form, Email, ERP.
    *   **Value**: Faster procurement cycle.

12. **Refund Approval Workflow**
    *   **Problem**: Agents issue refunds without checking policy/approvals.
    *   **Workflow**: Ticket Tagged "Refund Request" -> Check Order Value -> If > $100 Assign to Lead -> Lead Approves -> Stripe Refund Triggered.
    *   **Systems**: Zendesk, Stripe.
    *   **Value**: Prevents unauthorized revenue leakage.

13. **Daily Bank Balance Low Alert**
    *   **Problem**: Unexpected low balances cause bounced payments.
    *   **Workflow**: 8 AM Daily -> Check Plaid/Bank API Balance -> If < Threshold -> SMS CFO.
    *   **Systems**: Plaid API, Twilio.
    *   **Value**: Prevents overdraft fees and embarrassment.

14. **SaaS Cost Optimization**
    *   **Problem**: Paying for unused software seats.
    *   **Workflow**: Monthly -> Crawl Admin Usage Pages of SaaS Tools -> Identify Users with 0 Logins -> Add to "Downgrade" Sheet.
    *   **Systems**: OnWebApp Crawler, Google Sheets.
    *   **Value**: Reduces software spend by 10-15%.

15. **Contract Renewal Reminder**
    *   **Problem**: Missing renewal dates leads to unwanted auto-renewals.
    *   **Workflow**: Daily Scan of Contract Database -> If Expiry Date = Today + 60 -> Email Legal & Finance.
    *   **Systems**: Airtable/Database, Email.
    *   **Value**: Avoids lock-in to unwanted vendor contracts.

---

## 2. E-commerce
*Optimize inventory, monitor competitors, and enhance customer experience.*

16. **Multi-Channel Inventory Sync**
    *   **Problem**: Overselling on Amazon because Shopify stock didn't update.
    *   **Workflow**: Order on Shopify -> Calc New Stock -> Update Amazon/eBay Quantity -> Alert if Low.
    *   **Systems**: Shopify, Amazon Seller API, eBay.
    *   **Value**: Prevents stockouts and marketplace penalties.

17. **Competitor Price Monitor**
    *   **Problem**: Competitors undercut prices silently.
    *   **Workflow**: Hourly Crawl of Competitor URLs -> Extract Price -> If Lower, Auto-Adjust My Price (within floor).
    *   **Systems**: OnWebApp Crawler, Shopify.
    *   **Value**: Maintains price competitiveness.

18. **Automated Return Logistics**
    *   **Problem**: Manual return processing delays refunds and frustrates customers.
    *   **Workflow**: Return Form Submit -> Generate FedEx Label -> Email to Customer -> Create Support Ticket.
    *   **Systems**: Form, FedEx API, Zendesk.
    *   **Value**: Improves NPS and operational efficiency.

19. **VIP Customer Identification**
    *   **Problem**: High-spenders get generic treatment.
    *   **Workflow**: New Order -> Check Lifetime Value > $1k -> Tag "VIP" in CRM -> Trigger CEO Thank You Email.
    *   **Systems**: Shopify, HubSpot, Email.
    *   **Value**: Increases retention of top 1% customers.

20. **Negative Review Watchdog**
    *   **Problem**: Bad reviews go unanswered.
    *   **Workflow**: Daily Crawl (Amazon/Yelp) -> If Stars <= 2 -> Post to Slack Support Channel -> Create Jira Ticket.
    *   **Systems**: OnWebApp Crawler, Slack, Jira.
    *   **Value**: Rapid damage control.

21. **Abandoned Cart Recovery via SMS**
    *   **Problem**: Email open rates are dropping.
    *   **Workflow**: Cart Abandoned -> Wait 1 Hour -> Send SMS with 5% Discount Link.
    *   **Systems**: Shopify, Twilio.
    *   **Value**: Recovers revenue with 98% open rates.

22. **Dynamic Pricing based on Demand**
    *   **Problem**: Fixed prices don't capture peak demand value.
    *   **Workflow**: Check Google Trends/Site Traffic -> If Traffic > 2x Avg -> Increase Price by 5%.
    *   **Systems**: Google Analytics API, Shopify.
    *   **Value**: Maximizes margin during surges.

23. **New Product Launch Social Blast**
    *   **Problem**: Manually posting new products is tedious.
    *   **Workflow**: New SKU Published -> Generate Graphics -> Post to FB/Insta/Twitter with Buy Link.
    *   **Systems**: Shopify, Social Media APIs.
    *   **Value**: Instant traffic to new items.

24. **Low Stock Supplier Reorder**
    *   **Problem**: Forgetting to reorder bestsellers.
    *   **Workflow**: Inventory < Min Level -> Generate PDF Purchase Order -> Email Supplier.
    *   **Systems**: ERP, PDF Generator, Email.
    *   **Value**: Just-in-time inventory.

25. **Customer Lifetime Value (LTV) Calculation**
    *   **Problem**: Marketing doesn't know which channels bring high LTV.
    *   **Workflow**: Monthly -> Sum All Customer Orders -> Update "LTV" field in CRM -> Sync to Ad Platform.
    *   **Systems**: Database, Salesforce, Facebook Ads Custom Audience.
    *   **Value**: Better ad targeting.

26. **Fraud Detection Alert**
    *   **Problem**: Chargebacks from high-risk orders.
    *   **Workflow**: New Order -> Check IP Location vs Billing Address -> If Mismatch + High Value -> Slack Alert "Review Manually".
    *   **Systems**: Shopify, IP Geolocation API, Slack.
    *   **Value**: Reduces chargeback losses.

27. **Review Solicitation**
    *   **Problem**: Happy customers forget to review.
    *   **Workflow**: Order Status "Delivered" -> Wait 3 Days -> Send SMS/Email "How was it?".
    *   **Systems**: Shipping API, Email/SMS.
    *   **Value**: Increases social proof.

28. **Distributor Inventory Feed**
    *   **Problem**: Supplier sends inventory via CSV email daily.
    *   **Workflow**: Email Received -> Parse CSV Attachment -> Update Stock Levels in Store.
    *   **Systems**: Email, CSV Parser, WooCommerce.
    *   **Value**: Keeps dropshipping stock accurate.

29. **Influencer ROI Tracking**
    *   **Problem**: Unsure which influencers drive sales.
    *   **Workflow**: Coupon Code Used -> Add Sale Amount to "Influencer Sheet" -> Email Influencer Weekly Report.
    *   **Systems**: Shopify, Google Sheets, Email.
    *   **Value**: Transparent performance marketing.

30. **Product Image Optimization**
    *   **Problem**: Large images slow down the site.
    *   **Workflow**: Image Uploaded to Dropbox -> Resize/Compress -> Upload to CDN -> Update Product URL.
    *   **Systems**: Dropbox, Image Processing API, CMS.
    *   **Value**: Faster site speed and better SEO.

---

## 3. Sales
*Accelerate deal cycles and eliminate administrative drudgery.*

31. **Inbound Lead Routing (Round Robin)**
    *   **Problem**: Leads go cold waiting for assignment.
    *   **Workflow**: Form Submit -> Check Rep Availability -> Assign Round Robin -> Notify Rep App.
    *   **Systems**: Web Form, CRM, Push Notification.
    *   **Value**: Fastest speed-to-lead.

32. **Lead Enrichment & Qualification**
    *   **Problem**: Reps waste time researching prospects.
    *   **Workflow**: New Lead -> API Lookup (Clearbit) -> Add Size/Industry -> If Qualified, Move Pipeline Stage.
    *   **Systems**: CRM, Data Enrichment API.
    *   **Value**: Reps focus on best leads.

33. **Automated Contract Generation**
    *   **Problem**: Manual contract drafting has errors.
    *   **Workflow**: Deal "Contract Sent" -> Merge CRM Data into PDF -> Send via DocuSign.
    *   **Systems**: CRM, DocuSign.
    *   **Value**: Closing time reduced by 90%.

34. **Meeting Prep Brief**
    *   **Problem**: Reps enter meetings unprepared.
    *   **Workflow**: 1 Hr Before Meeting -> Crawl LinkedIn of Attendees -> Email Summary to Rep.
    *   **Systems**: Calendar, LinkedIn Crawl, Email.
    *   **Value**: Higher conversion rates.

35. **Stalled Deal Revival**
    *   **Problem**: Pipeline deals go dormant.
    *   **Workflow**: No Activity > 14 Days -> Send "Thinking of you" Email from Rep -> Task "Call Client".
    *   **Systems**: CRM, Email.
    *   **Value**: Revives zombie deals.

36. **New Lead SMS Alert**
    *   **Problem**: Hot leads need instant response.
    *   **Workflow**: Lead Score > 90 -> SMS Rep "Call [Name] Now!".
    *   **Systems**: CRM, Twilio.
    *   **Value**: Increases contact rate.

37. **Competitor Mention Alert**
    *   **Problem**: Reps don't know when competitors are mentioned in calls.
    *   **Workflow**: Call Transcript Ready -> Scan for Competitor Keywords -> Slack Rep "Competitor X mentioned".
    *   **Systems**: Gong/Otter API, Slack.
    *   **Value**: Enables rapid objection handling.

38. **Demo No-Show Follow-up**
    *   **Problem**: Rescheduling no-shows is manual work.
    *   **Workflow**: Zoom Meeting "Did Not Attend" -> Send Email "Sorry we missed you, reschedule here".
    *   **Systems**: Zoom, Email, Calendly.
    *   **Value**: Recovers lost meetings.

39. **Post-Sale Handover**
    *   **Problem**: Information lost between Sales and Success.
    *   **Workflow**: Deal Won -> Create Onboarding Project -> Email Intro to CSM -> Slack #wins.
    *   **Systems**: Salesforce, Asana, Slack.
    *   **Value**: Smoother customer transition.

40. **Territory Assignment**
    *   **Problem**: Manual assignment based on zip codes is tedious.
    *   **Workflow**: New Lead -> Check Zip Code Map -> Assign to Correct Territory Rep.
    *   **Systems**: CRM, Maps API.
    *   **Value**: Fair and fast lead distribution.

41. **Partner Portal Sync**
    *   **Problem**: Partners don't know deal status.
    *   **Workflow**: CRM Deal Updated -> Update Partner Portal Record -> Email Partner.
    *   **Systems**: Salesforce, PRM (Partner Relationship Mgmt).
    *   **Value**: Better partner engagement.

42. **Churn Risk Alert**
    *   **Problem**: CSMs don't notice usage drops.
    *   **Workflow**: Login Count < 1/week -> Create High Priority Task for CSM "Call Customer".
    *   **Systems**: App Database, CRM.
    *   **Value**: Proactive churn prevention.

43. **LinkedIn Connection Request**
    *   **Problem**: Reps forget to connect on social.
    *   **Workflow**: New Lead -> Create Task "Connect on LinkedIn" with Profile Link.
    *   **Systems**: CRM, Task Manager.
    *   **Value**: Builds multi-channel relationships.

44. **Proposal Expiry Reminder**
    *   **Problem**: Proposals expire without follow-up.
    *   **Workflow**: Sent Date + 7 Days -> Check Signed Status -> If No, Email Rep "Follow up on Proposal".
    *   **Systems**: DocuSign, Email.
    *   **Value**: Keeps deals moving.

45. **Sales Leaderboard Update**
    *   **Problem**: maintaining motivation.
    *   **Workflow**: Deal Won -> Update Google Slide Deck -> Post Screenshot to Slack.
    *   **Systems**: CRM, Google Slides, Slack.
    *   **Value**: Gamification drives performance.

---

## 4. Marketing
*Amplify reach and track performance without manual effort.*

46. **Content Cross-Posting**
    *   **Problem**: Copy-pasting blog posts to social.
    *   **Workflow**: RSS Feed Item -> Post to LinkedIn/Twitter/FB -> Slack #marketing.
    *   **Systems**: RSS, Social APIs.
    *   **Value**: Instant content amplification.

47. **Webinar Lead Sync**
    *   **Problem**: Attendees trapped in Zoom.
    *   **Workflow**: Webinar End -> Fetch Attendees -> Add to Mailchimp "Nurture" List.
    *   **Systems**: Zoom, Mailchimp.
    *   **Value**: Seamless lead nurturing.

48. **SEO Rank Monitor**
    *   **Problem**: SEO tools are expensive.
    *   **Workflow**: Daily Google Search -> Log Position -> Alert if Drop > 3 spots.
    *   **Systems**: OnWebApp Crawler, Sheets.
    *   **Value**: Cost-effective rank tracking.

49. **Social Sentiment Listener**
    *   **Problem**: Missing viral complaints.
    *   **Workflow**: Search Twitter for Brand -> Analyze Sentiment -> Alert Support if Negative.
    *   **Systems**: Twitter API, Slack.
    *   **Value**: Brand reputation protection.

50. **Ad Budget Guardian**
    *   **Problem**: Overspending on ads.
    *   **Workflow**: Check Ad Spend -> If > Daily Limit -> Pause Campaign -> SMS Marketer.
    *   **Systems**: FB/Google Ads, Twilio.
    *   **Value**: Prevents budget blowouts.

51. **Lead Magnet Delivery**
    *   **Problem**: Manual delivery of whitepapers.
    *   **Workflow**: Form Submit -> Email PDF Attachment -> Tag in CRM.
    *   **Systems**: Web Form, Email, CRM.
    *   **Value**: Instant gratification for leads.

52. **Eventbrite to CRM Sync**
    *   **Problem**: Event data siloed.
    *   **Workflow**: Ticket Sold -> Create/Update Contact in CRM -> Assign "Event" Tag.
    *   **Systems**: Eventbrite, Hubspot.
    *   **Value**: Unified customer view.

53. **UTM Performance Tracker**
    *   **Problem**: Manual CSV exports for reporting.
    *   **Workflow**: Daily -> Fetch GA4 Data by UTM -> Append to Master Sheet.
    *   **Systems**: Google Analytics 4, Sheets.
    *   **Value**: Automated reporting.

54. **User Generated Content (UGC) Finder**
    *   **Problem**: Finding customer photos is hard.
    *   **Workflow**: Monitor Instagram Hashtag -> If Image -> Post link to Slack #content.
    *   **Systems**: Instagram API, Slack.
    *   **Value**: Sourcing authentic content.

55. **Competitor Ad Watch**
    *   **Problem**: Not knowing competitor offers.
    *   **Workflow**: Weekly Crawl FB Ad Library -> Screenshot Ads -> Save to Drive.
    *   **Systems**: OnWebApp Crawler, Google Drive.
    *   **Value**: Competitive intelligence.

56. **Email List Cleaning**
    *   **Problem**: Bounces hurt deliverability.
    *   **Workflow**: Bounce Notification -> Remove from Active List -> Tag "Bounced".
    *   **Systems**: SendGrid, Database.
    *   **Value**: Maintains sender reputation.

57. **Marketing Asset Approval**
    *   **Problem**: Assets lost in email.
    *   **Workflow**: File Upload -> Slack Notification with Approve Button -> Move to DAM.
    *   **Systems**: Drive, Slack.
    *   **Value**: Streamlined creative ops.

58. **Newsletter Curated Content**
    *   **Problem**: Finding links for newsletters.
    *   **Workflow**: Monitor Industry RSS -> Save relevant articles to "Draft" Sheet.
    *   **Systems**: RSS, Sheets.
    *   **Value**: Faster content creation.

59. **Customer Testimonial Widget Updater**
    *   **Problem**: Website reviews are stale.
    *   **Workflow**: New 5-Star Review -> Update CMS Testimonial Database -> Clear Cache.
    *   **Systems**: Review Platform, CMS (WordPress/Webflow).
    *   **Value**: Fresh social proof.

60. **Offline Conversion Upload**
    *   **Problem**: Ads don't credit offline sales.
    *   **Workflow**: POS Transaction -> Format for Google Ads -> Upload Conversion via API.
    *   **Systems**: POS, Google Ads API.
    *   **Value**: Accurate ROAS measurement.

---

## 5. Operations
*Connect disjointed systems and ensure process compliance.*

61. **New Client Onboarding Folder Structure**
    *   **Problem**: Inconsistent file organization.
    *   **Workflow**: Deal Won -> Create Drive Folder Tree -> Copy Templates -> Share Link.
    *   **Systems**: CRM, Google Drive.
    *   **Value**: Standardized admin.

62. **Supply Chain Reorder Trigger**
    *   **Problem**: Production stops due to material shortage.
    *   **Workflow**: ERP Stock Check -> If < Limit -> Email Supplier.
    *   **Systems**: ERP, Email.
    *   **Value**: Business continuity.

63. **Legal Document Archiving**
    *   **Problem**: Contracts left in email.
    *   **Workflow**: DocuSign Complete -> Upload to Box -> Link in CRM.
    *   **Systems**: DocuSign, Box.
    *   **Value**: Audit readiness.

64. **Fleet Maintenance Scheduler**
    *   **Problem**: Vehicle breakdowns.
    *   **Workflow**: Odometer API Check -> If > Service Interval -> Task "Book Service" -> SMS Driver.
    *   **Systems**: Telematics, Task Mgmt, SMS.
    *   **Value**: Asset longevity.

65. **Compliance Certificate Expiry**
    *   **Problem**: Expired insurance stops work.
    *   **Workflow**: DB Check -> Expiry < 30 Days -> Email Vendor "Please Renew".
    *   **Systems**: Vendor DB, Email.
    *   **Value**: Risk mitigation.

66. **Daily Standup Reminder**
    *   **Problem**: People forget to post updates.
    *   **Workflow**: 9 AM -> Slack Bot "What are you working on?" -> Collate Replies.
    *   **Systems**: Slack.
    *   **Value**: Team alignment.

67. **Meeting Room Booking Display**
    *   **Problem**: Double bookings.
    *   **Workflow**: Calendar Event -> Push to Tablet Display API outside room.
    *   **Systems**: Google Calendar, IoT Display.
    *   **Value**: Office efficiency.

68. **Visitor Registration**
    *   **Problem**: Receptionist can't find host.
    *   **Workflow**: iPad Sign-in -> Slack Host "Guest Arrived" -> Print Badge.
    *   **Systems**: Envoy/Form, Slack, Printer API.
    *   **Value**: Professional visitor experience.

69. **Warehouse Temperature Alert**
    *   **Problem**: Spoilage of goods.
    *   **Workflow**: IoT Sensor Reading -> If Temp > Limit -> Call Manager via Twilio.
    *   **Systems**: IoT API, Twilio Voice.
    *   **Value**: Prevents inventory loss.

70. **Shift Scheduling Notification**
    *   **Problem**: Staff miss shifts.
    *   **Workflow**: Schedule Published -> SMS Staff their specific times.
    *   **Systems**: Scheduling Tool, Twilio.
    *   **Value**: Reduced absenteeism.

71. **Procurement Request Workflow**
    *   **Problem**: Unauthorized spending.
    *   **Workflow**: Form Request -> Manager Email Approval -> Create PO.
    *   **Systems**: Form, Email, ERP.
    *   **Value**: Spend control.

72. **IT Asset Tracking**
    *   **Problem**: Lost laptops.
    *   **Workflow**: "Device Assigned" Form -> Update Asset DB -> Email Employee Policy.
    *   **Systems**: Asset Panda/Sheet, Email.
    *   **Value**: Asset accountability.

73. **Monthly Report Generation**
    *   **Problem**: Days spent compiling reports.
    *   **Workflow**: 1st of Month -> Fetch Data (Sales, Ops, Marketing) -> Generate PDF -> Email to Board.
    *   **Systems**: Multiple APIs, PDF Generator.
    *   **Value**: Saves executive time.

74. **Office Supply Reorder**
    *   **Problem**: Running out of coffee/paper.
    *   **Workflow**: IoT Button Press -> Add Item to Amazon Cart -> Slack Office Mgr.
    *   **Systems**: IoT, Amazon, Slack.
    *   **Value**: Office happiness.

75. **Vendor Performance Scorecard**
    *   **Problem**: Subjective vendor evaluation.
    *   **Workflow**: Delivery Received -> Compare Date vs Promise -> Log Diff -> Quarterly Report.
    *   **Systems**: ERP, Sheets.
    *   **Value**: Data-driven vendor management.

---

## 6. QA & Testing
*Automate validation to ensure digital product quality.*

76. **Critical Path "Smoke Test"**
    *   **Problem**: Checkout breaks silently.
    *   **Workflow**: 15 Min Interval -> Headless Browser -> Add to Cart -> Verify Checkout Button -> Alert PagerDuty if Fail.
    *   **Systems**: OnWebApp Browser, PagerDuty.
    *   **Value**: Protects revenue.

77. **Broken Link Monitor**
    *   **Problem**: SEO penalties from 404s.
    *   **Workflow**: Weekly Crawl -> Identify 404s -> Create Jira Ticket.
    *   **Systems**: OnWebApp Crawler, Jira.
    *   **Value**: Site health.

78. **Visual Regression Testing**
    *   **Problem**: CSS bugs.
    *   **Workflow**: Deploy -> Screenshot Key Pages -> Diff vs Baseline -> Alert if Changed.
    *   **Systems**: Visual Tester, Slack.
    *   **Value**: UI Consistency.

79. **API Endpoint Validator**
    *   **Problem**: 3rd party API changes break app.
    *   **Workflow**: Hourly GET -> Validate Schema -> Log Errors.
    *   **Systems**: HTTP Client, Logger.
    *   **Value**: Reliability.

80. **Form Submission Verifier**
    *   **Problem**: Contact form stops sending emails.
    *   **Workflow**: Submit Form (Test Data) -> Check Inbox for Receipt -> Alert if Missing.
    *   **Systems**: Browser, Email Client.
    *   **Value**: Ensures leads aren't lost.

81. **Sitemap Validator**
    *   **Problem**: Sitemap errors hurt indexing.
    *   **Workflow**: Fetch Sitemap.xml -> Validate Structure -> Check all URLs 200 OK.
    *   **Systems**: XML Parser, HTTP Client.
    *   **Value**: SEO technical health.

82. **SSL Expiry Check**
    *   **Problem**: Security warnings scare users.
    *   **Workflow**: Daily Check Cert -> If Expiry < 30 Days -> Create Ops Ticket.
    *   **Systems**: SSL Checker, Jira.
    *   **Value**: Security compliance.

83. **Page Speed Monitor**
    *   **Problem**: Slow site kills conversion.
    *   **Workflow**: Daily Lighthouse Run -> Log Score -> Alert if Drop > 10 points.
    *   **Systems**: Lighthouse API, Sheets.
    *   **Value**: Performance optimization.

84. **Mobile Responsiveness Check**
    *   **Problem**: Mobile view breaks often.
    *   **Workflow**: Resize Browser to 375px -> Check Element Visibility -> Screenshot.
    *   **Systems**: Headless Browser.
    *   **Value**: Mobile UX assurance.

85. **404 Page Custom Content Check**
    *   **Problem**: Default server 404 pages look unprofessional.
    *   **Workflow**: Visit Random Bad URL -> Verify "Custom 404" Text Exists.
    *   **Systems**: HTTP Client.
    *   **Value**: Brand consistency.

86. **Third-Party Script Checker**
    *   **Problem**: Malware or unauthorized trackers.
    *   **Workflow**: Scan Page Scripts -> Compare Allowlist -> Alert if Unknown Script.
    *   **Systems**: HTML Parser.
    *   **Value**: Security.

87. **Database Backup Verification**
    *   **Problem**: Backups fail silently.
    *   **Workflow**: Check S3 Bucket -> Verify New File Exists & Size > 0 -> Slack "Backup Success".
    *   **Systems**: AWS S3 API, Slack.
    *   **Value**: Disaster recovery assurance.

88. **Critical User Path Test**
    *   **Problem**: Login/Dashboard flow breaks.
    *   **Workflow**: Login -> Load Dashboard -> Verify Data Load -> Logout.
    *   **Systems**: Browser Automation.
    *   **Value**: Core functionality check.

89. **Localization/Translation Check**
    *   **Problem**: Missing translation keys.
    *   **Workflow**: Crawl Spanish Site -> Check for English Strings -> Report.
    *   **Systems**: Crawler, Text Analyzer.
    *   **Value**: International UX.

90. **Load Time Anomaly Detection**
    *   **Problem**: Intermittent slowness.
    *   **Workflow**: Check Response Time every min -> If > 2s -> Log -> If 5x in row -> Alert.
    *   **Systems**: Monitor, PagerDuty.
    *   **Value**: Performance reliability.

---

## 7. HR
*Automate the employee lifecycle and improve internal culture.*

91. **Employee Onboarding Orchestration**
    *   **Problem**: New hires waiting for access.
    *   **Workflow**: ATS "Hired" -> Create Email/Slack/Jira Ticket -> Send Welcome Packet.
    *   **Systems**: ATS, Google Workspace, Slack.
    *   **Value**: Day 1 readiness.

92. **Leave Balance Sync**
    *   **Problem**: Scheduling conflicts.
    *   **Workflow**: HRIS Leave Approved -> Google Calendar OOO -> Slack Status "Away".
    *   **Systems**: HRIS, Calendar, Slack.
    *   **Value**: Visibility.

93. **Candidate Auto-Response & Routing**
    *   **Problem**: Ghosting candidates.
    *   **Workflow**: Application In -> Auto-Reply -> Parse Keywords -> Trello Card.
    *   **Systems**: Email, Trello.
    *   **Value**: Employer brand.

94. **Birthday & Anniversary Celebrations**
    *   **Problem**: Forgetting milestones.
    *   **Workflow**: Daily Check -> Post to Slack #general -> Send Gift Card.
    *   **Systems**: HR DB, Slack, GiftBit.
    *   **Value**: Culture & Morale.

95. **Payroll Hour Aggregation**
    *   **Problem**: Manual timesheet math.
    *   **Workflow**: Period End -> Fetch Harvest Time -> CSV for ADP -> Email HR.
    *   **Systems**: Time Tracking, Payroll.
    *   **Value**: Accuracy & Speed.

96. **Offboarding Workflow**
    *   **Problem**: Security risk from ex-employees.
    *   **Workflow**: Termination Date -> Suspend Google/Slack/VPN Access -> Email Return Label.
    *   **Systems**: Identity Provider, Logistics.
    *   **Value**: Security.

97. **Interview Scheduling**
    *   **Problem**: Email ping-pong.
    *   **Workflow**: Stage "Interview" -> Send Calendly Link -> Calendar Booked -> Update ATS.
    *   **Systems**: Calendly, ATS.
    *   **Value**: Efficiency.

98. **Employee Pulse Survey**
    *   **Problem**: Unknown sentiment.
    *   **Workflow**: Monthly -> Send Typeform -> Aggregate to Sheet -> Sentiment Analysis.
    *   **Systems**: Typeform, Sheets.
    *   **Value**: Feedback loop.

99. **Training Completion Reminder**
    *   **Problem**: Compliance training overdue.
    *   **Workflow**: LMS Check -> If Not Complete & Due < 3 Days -> Slack Reminder.
    *   **Systems**: LMS, Slack.
    *   **Value**: Compliance.

100. **Referral Bonus Tracker**
    *   **Problem**: Forgetting to pay referrals.
    *   **Workflow**: Candidate Hired (Source: Referral) -> Create Task "Pay Bonus in 90 Days".
    *   **Systems**: ATS, Task Mgmt.
    *   **Value**: Encourages referrals.

101. **Policy Acknowledgment Chase**
    *   **Problem**: Unsigned handbooks.
    *   **Workflow**: Weekly -> Check Unsigned -> Email Reminder with Link.
    *   **Systems**: DocuSign/HRIS, Email.
    *   **Value**: Legal compliance.

102. **Remote Equipment Stipend**
    *   **Problem**: Managing WFH expenses.
    *   **Workflow**: Form Request -> Check Eligibility -> Manager Approval -> Expensify.
    *   **Systems**: Form, Expensify.
    *   **Value**: Streamlined benefits.

103. **Visa/Work Permit Expiry**
    *   **Problem**: Legal risk of expired visas.
    *   **Workflow**: Monthly Check -> Expiry < 90 Days -> Alert HR & Employee.
    *   **Systems**: HRIS, Email.
    *   **Value**: Legal safety.

104. **Diversity Metrics Dashboard**
    *   **Problem**: Manual tracking of pipeline diversity.
    *   **Workflow**: Weekly -> Fetch ATS Data (Anonymized) -> Update Dashboard.
    *   **Systems**: ATS, BI Tool.
    *   **Value**: DEI Accountability.

105. **Slack Channel Archiver**
    *   **Problem**: Cluttered workspace.
    *   **Workflow**: Monthly -> Check Last Activity -> If > 90 Days -> Archive Channel.
    *   **Systems**: Slack API.
    *   **Value**: Organized communication.
