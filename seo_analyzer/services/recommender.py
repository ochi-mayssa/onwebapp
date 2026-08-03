ISSUE_RECOMMENDATIONS = {
    "Missing HTTPS Certificate": {
        "seo_impact": "Major ranking factor; browsers show security warnings; users may leave.",
        "business_impact": "Loss of trust, reduced traffic, lost conversions.",
        "recommended_fix": "Install/renew SSL certificate; redirect all HTTP traffic to HTTPS.",
        "priority": "critical",
    },
    "Missing Robots.txt": {
        "seo_impact": "Search engines may not know which pages to crawl/ignore.",
        "business_impact": "Potentially slower or incomplete indexation.",
        "recommended_fix": "Create a simple robots.txt file allowing crawling of all important pages.",
        "priority": "medium",
    },
    "Missing XML Sitemap": {
        "seo_impact": "Search engines may take longer to discover and index new/updated pages.",
        "business_impact": "Delayed indexation = delayed traffic.",
        "recommended_fix": "Generate and submit an XML sitemap to Google Search Console and Bing Webmaster Tools.",
        "priority": "high",
    },
    "Homepage Not Returning 200 OK": {
        "seo_impact": "Search engines will devalue or remove the homepage from index.",
        "business_impact": "Severe traffic loss; homepage is typically highest-traffic page.",
        "recommended_fix": "Fix the homepage immediately—check server logs for errors.",
        "priority": "critical",
    },
    "Missing Title Tag": {
        "seo_impact": "No clear page topic for search engines; lower rankings.",
        "business_impact": "Reduced organic traffic.",
        "recommended_fix": "Add a unique, descriptive title tag (30-60 chars) including target keywords.",
        "priority": "high",
    },
    "Title Tag Too Short (<30 chars)": {
        "seo_impact": "Less space for keywords; search engines may rewrite.",
        "business_impact": "Potentially lower CTR.",
        "recommended_fix": "Add more descriptive text to the title tag.",
        "priority": "medium",
    },
    "Title Tag Too Long (>60 chars)": {
        "seo_impact": "Search engines will truncate the title in results.",
        "business_impact": "Reduced CTR due to incomplete message.",
        "recommended_fix": "Shorten the title tag to 30-60 characters.",
        "priority": "medium",
    },
    "Missing Meta Description": {
        "seo_impact": "No compelling snippet for search results; search engines may rewrite.",
        "business_impact": "Potentially lower CTR.",
        "recommended_fix": "Add a unique, compelling meta description (50-320 chars) including a call to action.",
        "priority": "medium",
    },
    "Meta Description Too Short (<50 chars)": {
        "seo_impact": "Search engines may rewrite the snippet.",
        "business_impact": "Potentially lower CTR.",
        "recommended_fix": "Add more descriptive text to the meta description.",
        "priority": "low",
    },
    "Meta Description Too Long (>320 chars)": {
        "seo_impact": "Search engines will truncate the snippet.",
        "business_impact": "Reduced CTR.",
        "recommended_fix": "Shorten the meta description to 50-320 characters.",
        "priority": "low",
    },
    "Missing H1 Tag": {
        "seo_impact": "No clear primary topic for the page; lower rankings.",
        "business_impact": "Reduced organic traffic.",
        "recommended_fix": "Add exactly one descriptive H1 tag including the primary target keyword.",
        "priority": "high",
    },
    "Multiple H1 Tags": {
        "seo_impact": "Confuses search engines about the primary topic.",
        "business_impact": "Potentially lower rankings.",
        "recommended_fix": "Change extra H1 tags to H2/H3 tags.",
        "priority": "medium",
    },
    "Missing Canonical Tag": {
        "seo_impact": "Risk of duplicate content penalties.",
        "business_impact": "Split ranking signals across duplicate URLs.",
        "recommended_fix": "Add a self-referencing canonical tag to every page.",
        "priority": "high",
    },
    "Canonical Tag Mismatch": {
        "seo_impact": "Page may not be indexed at all; severe ranking loss.",
        "business_impact": "Zero or drastically reduced organic traffic for this page.",
        "recommended_fix": "Update the canonical tag to point to the page's final URL.",
        "priority": "critical",
    },
    "Noindex Tag Present": {
        "seo_impact": "Page will not be indexed by search engines.",
        "business_impact": "Zero organic traffic for this page.",
        "recommended_fix": "Remove the noindex tag unless you intentionally want to hide the page.",
        "priority": "critical",
    },
    "Slow Response Time (>3s)": {
        "seo_impact": "Ranking factor; poor user experience.",
        "business_impact": "Higher bounce rates, lower conversions.",
        "recommended_fix": "Optimize server performance, enable caching, compress images.",
        "priority": "medium",
    },
    "Large Page Size (>2MB)": {
        "seo_impact": "Slower load times; uses more crawl budget.",
        "business_impact": "Higher bounce rates, lower conversions.",
        "recommended_fix": "Compress images, minify CSS/JS, remove unnecessary content.",
        "priority": "low",
    },
    "Thin Content (<300 words)": {
        "seo_impact": "Lacks depth; search engines may not consider it valuable.",
        "business_impact": "Lower rankings, reduced organic traffic.",
        "recommended_fix": "Add valuable, unique content to reach at least 300 words.",
        "priority": "medium",
    },
    "Missing Image Alt Text": {
        "seo_impact": "Images won't rank in image search; reduced accessibility.",
        "business_impact": "Lost image search traffic; accessibility issues for screen readers.",
        "recommended_fix": "Add descriptive alt text to all images (empty alt for decorative images).",
        "priority": "medium",
    },
}


def get_recommendation(issue_name):
    """Get recommendation data for a given issue name"""
    return ISSUE_RECOMMENDATIONS.get(issue_name, {
        "seo_impact": "",
        "business_impact": "",
        "recommended_fix": "",
        "priority": "medium",
    })
