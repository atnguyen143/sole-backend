# Project Guidelines

## MCP Tools Available

I have access to the following MCP servers configured in ~/.claude.json:

- **supabase**: Database queries and product searches
- **stockx**: StockX API integration
- **alias**: Custom aliases
- **n8n-mcp**: n8n workflow automation

Use these MCP tools instead of curl to Heroku endpoints.

## File Organization Rules

**NEVER create multiple scripts for the same task.** Consolidate into ONE unified script per task.

### Project Structure
```
sole-backend/
├── scripts/
│   ├── active/          # Production scripts only
│   ├── testing/         # Testing/validation only
│   └── deprecated/      # Old versions (reference only)
├── sql/                 # Database schemas
└── docs/                # Documentation
```

### Before Creating New Files

1. **Check if similar script exists** - Search `scripts/active/` first
2. **Update existing script** - Don't create v2, v3, etc.
3. **One script per task** - Example: `migrate_alias_remaining.py` not `migrate_alias_v1.py`, `migrate_alias_v2.py`, `migrate_alias_fast.py`
4. **Documentation in docs/** - Don't create duplicate README files

### Script Naming Convention

✅ **Good:**
- `migrate_alias_remaining.py` (clear, specific)
- `create_product_mappings.py` (action + subject)
- `test_similarity_thresholds.py` (testing prefix)

❌ **Bad:**
- `migrate_alias_v2.py` (version in name)
- `migrate_alias_fast.py` (implementation detail)
- `create_indexes_safe.py` (redundant qualifier)

### When to Create New Script

**Only create new scripts if:**
1. Completely different task
2. Different use case (e.g., testing vs production)
3. Moving to `deprecated/` folder first

**Never create:**
- Multiple versions of the same script
- "Fast" or "safe" variants
- Incremental v1, v2, v3 versions

### Cleanup Process

When improving a script:
1. Update the existing file in-place
2. Move old version to `deprecated/` if needed
3. Update `docs/README.md` with changes
4. **Never** leave multiple active versions
