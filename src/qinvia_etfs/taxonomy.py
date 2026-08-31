"""Transparent, name-based taxonomy for the free ETF research universe.

The source catalogue does not contain a reliable active/passive flag or a
complete institutional category.  This module therefore classifies only what
can be supported by the free fields we have and records the evidence used for
every label.  ``not_determined`` is intentional: it is preferable to false
precision.
"""

from __future__ import annotations

from html import unescape
import re
from typing import Iterable


TAXONOMY_VERSION = "etf_taxonomy_1.1"


def _clean(value: object) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _matches(text: str, patterns: Iterable[tuple[str, str]]) -> tuple[str, str] | None:
    for label, pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return label, pattern
    return None


COMMODITY_PATTERNS = (
    ("precious_metals", r"\b(gold|silver|platinum|palladium|precious metals?)\b"),
    ("industrial_metals", r"\b(copper|base metals?|industrial metals?|lithium|rare earth|uranium)\b"),
    ("energy_commodities", r"\b(crude oil|oil fund|natural gas|gasoline|brent|wti|energy commodity)\b"),
    ("agriculture", r"\b(agricultur|corn|wheat|soybean|sugar|coffee|cocoa|cotton|livestock|cattle|grain)\w*\b"),
    ("broad_commodities", r"\b(commodity|commodities|dbci|gsci)\b"),
)

FIXED_INCOME_PATTERNS = (
    ("cash_and_t_bills", r"\b(t[ -]?bills?|treasury bills?|cash (?:management|reserve|equivalents?)|money market|0-3 month|1-3 month|3-12 month)\b"),
    ("municipal_bonds", r"\b(municipal|muni)\b"),
    ("high_yield_bonds", r"\b(high yield|junk bond|fallen angels?)\b"),
    ("loans_and_clo", r"\b(CLO|senior loans?|bank loans?|floating rate|leveraged loans?)\b"),
    ("mortgage_and_securitized", r"\b(mortgage|MBS|securitized|asset backed|CMBS)\b"),
    ("inflation_linked", r"\b(TIPS|inflation[- ]protected|inflation linked)\b"),
    ("emerging_market_debt", r"\b(emerging markets?.*(bond|debt)|local debt|emerging.*sovereign)\b"),
    ("treasury_and_government", r"\b(treasur|government bond|sovereign bond)\w*\b"),
    ("corporate_bonds", r"\b(corporate|investment grade|credit)\b"),
    ("aggregate_bonds", r"\b(aggregate bond|total bond|core bond|fixed income)\b"),
    ("income_and_hybrid_securities", r"\b(short maturity|ultra[- ]short income|core plus income|strategic income|convertible securities|preferred (?:stock|securities|income|ETF))\b"),
)

ALTERNATIVE_PATTERNS = (
    ("long_short_market_neutral", r"\b(long[ /-]?short|market neutral|anti[- ]beta|hedged equity index option|simplify hedged equity)\b"),
    ("managed_futures", r"\b(managed futures?|trend following)\b"),
    ("merger_arbitrage", r"\b(merger arbitrage|arbitrage)\b"),
    ("absolute_return", r"\b(absolute return|alternative return)\b"),
    ("alternative_income", r"\b(alternative income|closed[- ]end funds?)\b"),
    ("risk_managed_alternative", r"\b(alternative|defined risk|managed risk|black ?swan|long/flat|deflation|inflation hedge)\b"),
)

SECTOR_PATTERNS = (
    ("semiconductors", r"\b(semiconductor|chipmakers?|chip)\w*\b"),
    ("technology", r"\b(technology|software|internet|cloud computing|cybersecurity|fintech|digital economy)\b"),
    ("communications", r"\b(communication services?|telecom|media)\b"),
    ("healthcare_biotech", r"\b(health ?care|biotech|pharma|medical devices?|genomic|clinical trials?)\b"),
    ("financials", r"\b(financials?|banks?|insurance|capital markets?|fintech)\b"),
    ("real_estate", r"\b(real estate|REITs?|homebuilders?|mortgage real estate)\b"),
    ("energy", r"\b(energy|oil & gas|oil and gas|midstream|MLP|solar|wind power)\b"),
    ("materials_and_mining", r"\b(materials?|miners?|mining|metals?|steel|uranium|lithium|rare earth|timber)\b"),
    ("industrials_transport", r"\b(industrials?|transportation|aerospace|airlines?|railroad|shipping|infrastructure)\b"),
    ("defense_aerospace", r"\b(defen[cs]e|aerospace|military)\b"),
    ("consumer_discretionary", r"\b(consumer discretionary|retail|travel|leisure|gaming|automotive|restaurants?)\b"),
    ("consumer_staples", r"\b(consumer staples?|food & beverage|food and beverage|agriculture)\b"),
    ("utilities", r"\b(utilit(?:y|ies)|electric power)\b"),
)

THEME_PATTERNS = (
    ("artificial_intelligence", r"\b(artificial intelligence|\bAI\b|robotics|automation)\b"),
    ("clean_energy_climate", r"\b(clean energy|clean power|climate|decarbon|carbon|solar|wind energy|hydrogen)\w*\b"),
    ("digital_disruption", r"\b(blockchain|cloud computing|cybersecurity|digital transformation|e-commerce|internet|fintech)\b"),
    ("mobility", r"\b(electric vehicles?|autonomous|future transportation|mobility)\b"),
    ("infrastructure", r"\b(infrastructure|smart grid|water)\b"),
    ("demographics", r"\b(aging|millennial|longevity|population)\b"),
    ("natural_resources", r"\b(natural resources?|timber|agriculture|metals?|miners?|mining|uranium|lithium)\b"),
    ("defense_security", r"\b(defen[cs]e|aerospace|cybersecurity|security)\b"),
    ("other_thematic", r"\b(disrupt|innovation|next gen|future|revolution|transformational|thematic)\w*\b"),
)

GEOGRAPHY_PATTERNS = (
    ("emerging_markets", r"\b(emerging markets?|frontier markets?)\b"),
    ("china", r"\b(china|chinese|hong kong)\b"),
    ("india", r"\bindia(n)?\b"),
    ("japan", r"\bjapan(ese)?\b"),
    ("europe", r"\b(europe|eurozone|germany|france|italy|spain|switzerland|united kingdom|UK)\b"),
    ("asia_pacific", r"\b(asia|pacific|australia|new zealand|korea|taiwan|singapore)\b"),
    ("latin_america", r"\b(latin america|brazil|mexico|argentina|chile|colombia)\b"),
    ("international_ex_us", r"\b(international|global ex|world ex|ex[- ]?U\.?S\.?|EAFE|ACWI ex)\b"),
    ("global", r"\b(global|world|ACWI)\b"),
    ("united_states", r"\b(U\.?S\.?|United States|S&P 500|Russell|Dow 30|Nasdaq[- ]?100)\b"),
)

ACTIVE_EXPLICIT = (
    ("active_word", r"\b(active|actively managed)\b"),
    ("active_builders", r"\bActiveBuilders\b"),
    ("managed_strategy", r"\b(managed futures?|managed municipal|managed risk)\b"),
    ("discretionary_strategy", r"\b(tactical|opportunistic|absolute return|long[ /-]?short|market neutral|merger arbitrage)\b"),
)

ACTIVE_SPONSORS = (
    ("active_sponsor_capital_group", r"\bCapital Group\b"),
    ("active_sponsor_ark", r"\bARK(?: |$)"),
    ("active_sponsor_avantis", r"\bAvantis\b"),
    ("active_sponsor_dimensional", r"\bDimensional\b"),
    ("active_sponsor_t_rowe", r"\bT\.? Rowe Price\b"),
    ("active_sponsor_davis", r"\bDavis Select\b"),
    ("active_sponsor_advisorshares", r"\bAdvisorShares\b"),
)

INDEX_PROVIDER = r"\b(Index|S&P|MSCI|Russell|Nasdaq|FTSE|Dow Jones|Bloomberg|Morningstar|STOXX|AlphaDEX|Indxx|MarketVector)\b"
RULES_PATTERN = r"\b(factor|multifactor|dividend|value|growth|momentum|quality|low volatility|min(?:imum)? vol|equal weight|fundamental|smart beta|ActiveBeta|cash cows?|wide moat|ESG|tilt|rotation)\b"


def classify_product(name: object, asset_classes: object = "") -> dict[str, str]:
    """Return a mutually exclusive top-level taxonomy plus auditable evidence."""

    clean_name = _clean(name)
    text = f" {clean_name} "
    source_assets = {part.strip() for part in str(asset_classes or "").split("|") if part.strip()}
    evidence: list[str] = []

    alternative = _matches(text, ALTERNATIVE_PATTERNS)
    commodity = _matches(text, COMMODITY_PATTERNS)
    fixed_income = _matches(text, FIXED_INCOME_PATTERNS)

    if "crypto" in source_assets or re.search(r"\b(bitcoin|ether|ethereum|crypto|digital asset)\w*\b", text, re.I):
        asset_class = "crypto"
        evidence.append("asset:crypto")
    elif "currency" in source_assets or re.search(r"\b(currency|currencies|dollar|euro|yen|renminbi|forex)\b", text, re.I):
        asset_class = "currency"
        evidence.append("asset:currency")
    elif "commodity" in source_assets or commodity:
        asset_class = "commodity"
        evidence.append("asset:commodity")
    elif "fixed_income" in source_assets or fixed_income:
        asset_class = "fixed_income"
        evidence.append("asset:fixed_income")
    elif "real_estate" in source_assets or re.search(r"\b(real estate|REITs?)\b", text, re.I):
        asset_class = "real_estate"
        evidence.append("asset:real_estate")
    elif "multi_asset" in source_assets or re.search(r"\b(multi[- ]asset|asset allocation|allocation ETF)\b", text, re.I):
        asset_class = "multi_asset"
        evidence.append("asset:multi_asset")
    elif "alternatives" in source_assets or alternative:
        asset_class = "alternatives"
        evidence.append("asset:alternatives")
    elif "equity" in source_assets:
        asset_class = "equity"
        evidence.append("asset:equity")
    else:
        # Most still-unknown products are identifiable from the legal/name
        # vocabulary.  This inference remains medium confidence.
        if re.search(r"\b(equity|companies|stock|shares|large cap|mid cap|small cap|microcap|sector|industry)\b", text, re.I):
            asset_class = "equity"
            evidence.append("asset:name_equity")
        elif (
            _matches(text, SECTOR_PATTERNS)
            or _matches(text, THEME_PATTERNS)
            or _matches(text, GEOGRAPHY_PATTERNS)
            or re.search(INDEX_PROVIDER, text, re.I)
            or re.search(RULES_PATTERN, text, re.I)
            or re.search(r"\b(ETF|equity index fund|stock fund|company fund)\b", text, re.I)
        ):
            asset_class = "equity"
            evidence.append("asset:name_inferred_equity")
        else:
            asset_class = "unknown"
            evidence.append("asset:unknown")

    if asset_class == "commodity":
        exposure_type = commodity[0] if commodity else "other_commodity"
        evidence.append(f"exposure:{exposure_type}")
    elif asset_class == "fixed_income":
        exposure_type = fixed_income[0] if fixed_income else "other_fixed_income"
        evidence.append(f"exposure:{exposure_type}")
    elif asset_class == "alternatives":
        exposure_type = alternative[0] if alternative else "other_alternative"
        evidence.append(f"exposure:{exposure_type}")
    elif asset_class in {"crypto", "currency", "real_estate", "multi_asset"}:
        exposure_type = asset_class
        evidence.append(f"exposure:{exposure_type}")
    else:
        sector = _matches(text, SECTOR_PATTERNS)
        theme = _matches(text, THEME_PATTERNS)
        if sector:
            exposure_type = "sector_or_industry"
            evidence.append(f"sector:{sector[0]}")
        elif theme:
            exposure_type = "thematic_equity"
            evidence.append(f"theme:{theme[0]}")
        elif re.search(r"\b(S&P 500|total (?:stock )?market|broad market|Russell 1000|Russell 3000|Dow Jones U\.?S\.?|core S&P)\b", text, re.I):
            exposure_type = "broad_equity"
            evidence.append("exposure:broad_equity")
        elif re.search(RULES_PATTERN, text, re.I):
            exposure_type = "factor_style_or_income"
            evidence.append("exposure:factor_style_or_income")
        else:
            exposure_type = "other_equity" if asset_class == "equity" else "unclassified"
            evidence.append(f"exposure:{exposure_type}")

    sector_match = _matches(text, SECTOR_PATTERNS)
    sector_theme = sector_match[0] if sector_match else "not_sector_specific"
    theme_match = _matches(text, THEME_PATTERNS)
    theme = theme_match[0] if theme_match else "not_thematic"
    geography_match = _matches(text, GEOGRAPHY_PATTERNS)
    geography = geography_match[0] if geography_match else "not_determined"

    if alternative:
        primary_strategy = alternative[0]
    elif re.search(r"\b(covered call|buywrite|option income|premium income|collar|putwrite)\b", text, re.I):
        primary_strategy = "options_income_or_overlay"
    elif re.search(r"\b(target maturity|term (?:corporate|treasury|municipal)|bulletshares|ibonds)\b", text, re.I):
        primary_strategy = "target_maturity"
    elif asset_class == "multi_asset":
        primary_strategy = "asset_allocation"
    elif asset_class == "commodity":
        primary_strategy = exposure_type
    elif asset_class == "fixed_income":
        primary_strategy = exposure_type
    elif re.search(r"\b(dividend|income|yield)\b", text, re.I):
        primary_strategy = "dividend_or_income"
    elif re.search(r"\b(value|growth|momentum|quality|low volatility|min(?:imum)? vol|factor|multifactor|equal weight|fundamental|cash cows?|wide moat)\b", text, re.I):
        primary_strategy = "factor_or_style"
    elif exposure_type == "sector_or_industry":
        primary_strategy = "sector_or_industry"
    elif exposure_type == "thematic_equity":
        primary_strategy = "thematic_equity"
    elif exposure_type == "broad_equity":
        primary_strategy = "broad_equity"
    else:
        primary_strategy = exposure_type

    explicit_active = _matches(text, ACTIVE_EXPLICIT)
    sponsor_active = _matches(text, ACTIVE_SPONSORS)
    has_index = bool(re.search(INDEX_PROVIDER, text, re.I))
    has_rules = bool(re.search(RULES_PATTERN, text, re.I))
    # ActiveBeta is a brand for systematic beta, not evidence of discretion.
    activebeta = bool(re.search(r"\bActiveBeta\b", text, re.I))
    if explicit_active and not activebeta:
        management_style = "active_identified"
        management_evidence = explicit_active[0]
        management_confidence = "high"
    elif sponsor_active and not has_index:
        management_style = "active_identified"
        management_evidence = sponsor_active[0]
        management_confidence = "medium"
    elif has_rules:
        management_style = "systematic_or_rules_based"
        management_evidence = "rules_keyword"
        management_confidence = "medium"
    elif has_index:
        management_style = "index_passive_identified"
        management_evidence = "index_provider_or_index_word"
        management_confidence = "high"
    else:
        management_style = "not_determined"
        management_evidence = "free_metadata_insufficient"
        management_confidence = "low"

    evidence.extend(
        [
            f"management:{management_evidence}",
            f"geography:{geography}",
            f"theme:{theme}",
        ]
    )
    taxonomy_confidence = "low" if asset_class == "unknown" else ("high" if management_confidence == "high" else "medium")
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "normalized_name": clean_name,
        "asset_class_refined": asset_class,
        "exposure_type": exposure_type,
        "primary_strategy": primary_strategy,
        "sector_theme": sector_theme,
        "theme": theme,
        "geography": geography,
        "management_style": management_style,
        "management_confidence": management_confidence,
        "taxonomy_confidence": taxonomy_confidence,
        "taxonomy_evidence": "|".join(evidence),
    }
