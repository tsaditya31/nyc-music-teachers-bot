# Heartbeat Configuration

## Cycle: Every 1 hour

### Every Cycle (hourly)
1. **Re-crawl stale sources**: Find active sources not crawled in 24h, crawl them, extract activities
2. **Evaluate pending sources**: Fetch and evaluate any pending sources, activate or reject them

### Every 6th Cycle (~6 hours)
3. **Discover new sources**: Pick a rotating category, search the web for new listing sites
   - Categories rotate: music → sports → art → STEM → dance → theater → coding → swimming → martial arts → gymnastics → tutoring → language → cooking → nature

### Every 24th Cycle (~daily)
4. **Expire old activities**: Mark activities not seen in 30+ days as expired
5. **Update memory summaries**: Write current stats and recent decisions to memory files

## Execution Rules
- Tasks run serially (one at a time) to avoid API rate limits
- Each crawl session limited to 10 pages per source
- Discovery limited to 5 candidate URLs per category
- Log all decisions to memory/decisions.md
- Update memory/sources.md after any source changes
