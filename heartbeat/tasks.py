"""Heartbeat task definitions — each task is an autonomous agent call."""

import json
import logging
import anthropic
import config
import skills  # noqa: F401
from brain import orchestrator
from db.queries import sources, activities as activities_q, crawl_log
from skills.tag_location import tag_location_skill

logger = logging.getLogger(__name__)


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)


async def crawl_stale_sources():
    """Re-crawl active sources that are stale."""
    stale = await sources.get_stale_sources(config.STALE_SOURCE_HOURS)
    if not stale:
        logger.info("Heartbeat: no stale sources to crawl")
        return

    logger.info(f"Heartbeat: found {len(stale)} stale sources to crawl")
    for source in stale[:3]:  # Limit to 3 per cycle to control costs
        await _crawl_single_source(source)


async def _crawl_single_source(source: dict):
    """Crawl a single source: fetch HTML, extract activities, tag locations, upsert."""
    source_id = source["id"]
    url = source["url"]
    logger.info(f"Crawling source {source_id}: {url}")

    crawl_id = await crawl_log.start_crawl(source_id)
    total_found = 0
    total_new = 0
    total_updated = 0
    total_tokens = 0

    try:
        # Use the brain to orchestrate the crawl
        messages = [{
            "role": "user",
            "content": (
                f"Crawl this source and extract all kids activities: {url}\n"
                f"Source ID: {source_id}\n\n"
                "Steps:\n"
                "1. Use crawl_source to fetch the page HTML\n"
                "2. Use extract_activities to get structured data from the HTML\n"
                "3. For each activity, use tag_location on the address to get ZIP/neighborhood/borough\n"
                "4. Report what you found\n\n"
                "After extraction, tell me the count and a brief summary."
            ),
        }]

        response = await orchestrator.run(
            client=_client(),
            messages=messages,
            mode="crawl",
            max_turns=10,
        )

        # The orchestrator executed the skills inline via tool calls.
        # Now we need to actually persist the extracted activities.
        # The brain's tool calls already ran extract_activities and tag_location.
        # We'll do a direct extraction path as well for reliability.
        await _direct_crawl_and_persist(source_id, url, crawl_id)

        await sources.update_source(source_id, last_crawled_at="NOW()")
        logger.info(f"Crawl complete for source {source_id}")

    except Exception as e:
        logger.exception(f"Crawl failed for source {source_id}")
        await crawl_log.finish_crawl(
            crawl_id, status="error", error_message=str(e)
        )
        # Decrease reliability
        new_score = max(0.0, (source.get("reliability_score") or 0.5) - 0.1)
        await sources.update_source(source_id, reliability_score=new_score)


async def _direct_crawl_and_persist(source_id: int, url: str, crawl_id: int):
    """Direct crawl path: fetch → extract → tag → upsert."""
    from skills.crawl_source import crawl_source_skill
    from skills.extract_activities import extract_activities_skill

    # Fetch
    html = await crawl_source_skill(url=url, use_browser=True)
    if html.startswith("Error"):
        await crawl_log.finish_crawl(crawl_id, status="error", error_message=html)
        return

    # Extract
    result_str = await extract_activities_skill(html=html, source_url=url)
    result = json.loads(result_str)

    if "error" in result:
        await crawl_log.finish_crawl(crawl_id, status="error", error_message=result["error"])
        return

    extracted = result.get("activities", [])
    tokens = result.get("tokens_used", 0)

    total_new = 0
    total_updated = 0

    for act in extracted:
        # Tag location
        address = act.get("address") or act.get("location_name") or ""
        loc_str = await tag_location_skill(address=address)
        loc = json.loads(loc_str)

        # Upsert
        activity_id, is_new = await activities_q.upsert_activity(
            name=act.get("name", "Unknown Activity"),
            source_url=url,
            source_id=source_id,
            description=act.get("description"),
            category=act.get("category"),
            subcategory=act.get("subcategory"),
            age_range=act.get("age_range"),
            location_name=act.get("location_name"),
            address=act.get("address"),
            zip_code=loc.get("zip_code"),
            neighborhood=loc.get("neighborhood"),
            borough=loc.get("borough"),
            price=act.get("price"),
            schedule=act.get("schedule"),
            contact_email=act.get("contact_email"),
            contact_phone=act.get("contact_phone"),
            website=act.get("website"),
            tags=act.get("tags", []),
        )
        if is_new:
            total_new += 1
        else:
            total_updated += 1

    await crawl_log.finish_crawl(
        crawl_id,
        status="success",
        pages_crawled=1,
        activities_found=len(extracted),
        activities_new=total_new,
        activities_updated=total_updated,
        tokens_used=tokens,
    )
    await sources.update_source(source_id, last_crawled_at="NOW()")
    logger.info(
        f"Source {source_id}: found {len(extracted)}, new {total_new}, updated {total_updated}"
    )


async def evaluate_pending_sources():
    """Evaluate pending sources and activate or reject them."""
    pending = await sources.get_pending_sources()
    if not pending:
        logger.info("Heartbeat: no pending sources")
        return

    logger.info(f"Heartbeat: evaluating {len(pending)} pending sources")
    messages = [{
        "role": "user",
        "content": (
            "Evaluate these pending sources and decide whether to activate or reject each one:\n\n"
            + "\n".join(f"- ID {s['id']}: {s['url']} (category: {s.get('category', 'unknown')})"
                       for s in pending)
            + "\n\nFor each source:\n"
            "1. Use crawl_source to fetch the page\n"
            "2. Use evaluate_source to assess it\n"
            "3. Use manage_sources to update its status to 'active' or 'rejected'\n"
            "4. Log your decision to memory using memory_write (file: decisions.md)"
        ),
    }]

    await orchestrator.run(
        client=_client(),
        messages=messages,
        mode="heartbeat",
        max_turns=15,
    )


async def discover_new_sources(category: str):
    """Discover new source URLs for a given category."""
    logger.info(f"Heartbeat: discovering sources for category '{category}'")
    messages = [{
        "role": "user",
        "content": (
            f"Discover new websites that list kids {category} activities in NYC.\n\n"
            "Steps:\n"
            "1. Use discover_sources to search the web\n"
            "2. For each candidate URL, use manage_sources to add it as a pending source\n"
            "3. Log what you found to memory (file: decisions.md)\n"
            "4. Summarize what you discovered"
        ),
    }]

    await orchestrator.run(
        client=_client(),
        messages=messages,
        mode="discovery",
        max_turns=10,
    )


async def expire_old_activities():
    """Expire activities not seen in 30+ days."""
    count = await activities_q.expire_old_activities(config.EXPIRE_ACTIVITY_DAYS)
    logger.info(f"Heartbeat: expired {count} old activities")
