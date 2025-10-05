# Auto-Generate Embeddings in Supabase

## Storing API Keys as Supabase Secrets

### Option A: Supabase Vault (Encrypted Database Storage)

```sql
-- Store API key in Supabase Vault (encrypted at rest)
SELECT vault.create_secret('YOUR_API_KEY_HERE', 'openrouter_api_key');

-- Retrieve in SQL functions
SELECT decrypted_secret
FROM vault.decrypted_secrets
WHERE name = 'openrouter_api_key';
```

### Option B: Edge Function Environment Variables

```bash
# Set secrets for Edge Functions (via Supabase CLI)
supabase secrets set OPENROUTER_API_KEY=your_key_here

# List all secrets
supabase secrets list

# Use in Edge Function
const apiKey = Deno.env.get('OPENROUTER_API_KEY')
```

---

## Using OpenRouter Instead of OpenAI

**OpenRouter API endpoint:** `https://openrouter.ai/api/v1/chat/completions`

**For embeddings, OpenRouter supports:**
- `text-embedding-3-small` (OpenAI)
- `text-embedding-3-large` (OpenAI)
- Other providers' embedding models

**Example API call:**
```typescript
const response = await fetch('https://openrouter.ai/api/v1/embeddings', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${OPENROUTER_API_KEY}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    model: 'openai/text-embedding-3-small',
    input: embedding_text,
  })
})
```

---

## Option 1: Database Trigger + Edge Function (RECOMMENDED)

**How it works:**
1. Create Supabase Edge Function that calls OpenAI API
2. Create database trigger that fires on INSERT/UPDATE
3. Trigger calls Edge Function to generate embedding

**Pros:**
- Fully automated
- No external scripts needed
- Real-time embedding generation

**Cons:**
- Costs per API call (~$0.00002 per product)
- Requires Edge Function deployment

**Setup:**

### 1. Create Edge Function

```bash
# In your project
supabase functions new generate-embedding
```

```typescript
// supabase/functions/generate-embedding/index.ts
import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'

serve(async (req) => {
  const { embedding_text } = await req.json()

  // Get API key from environment (set via: supabase secrets set)
  const apiKey = Deno.env.get('OPENROUTER_API_KEY') || Deno.env.get('OPENAI_API_KEY')

  // Use OpenRouter (or OpenAI if using OPENAI_API_KEY)
  const apiUrl = Deno.env.get('OPENROUTER_API_KEY')
    ? 'https://openrouter.ai/api/v1/embeddings'
    : 'https://api.openai.com/v1/embeddings'

  const response = await fetch(apiUrl, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'openai/text-embedding-3-small',  // OpenRouter format
      input: embedding_text,
    })
  })

  const data = await response.json()
  const embedding = data.data[0].embedding

  return new Response(
    JSON.stringify({ embedding }),
    { headers: { 'Content-Type': 'application/json' } }
  )
})
```

### 2. Deploy Edge Function

```bash
supabase functions deploy generate-embedding --no-verify-jwt
```

### 3. Create Database Trigger

```sql
-- Function to call Edge Function
CREATE OR REPLACE FUNCTION auto_generate_embedding()
RETURNS TRIGGER AS $$
DECLARE
  edge_function_url TEXT;
  embedding_result JSONB;
BEGIN
  -- Only generate if embedding_text exists and embedding is NULL
  IF NEW.embedding_text IS NOT NULL AND NEW.embedding IS NULL THEN

    -- Call Edge Function
    edge_function_url := 'https://YOUR_PROJECT_REF.supabase.co/functions/v1/generate-embedding';

    SELECT content::jsonb INTO embedding_result
    FROM http((
      'POST',
      edge_function_url,
      ARRAY[http_header('Content-Type', 'application/json')],
      'application/json',
      json_build_object('embedding_text', NEW.embedding_text)::text
    ));

    -- Set embedding
    NEW.embedding := (embedding_result->>'embedding')::vector;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger on INSERT/UPDATE
CREATE TRIGGER trigger_auto_generate_embedding
BEFORE INSERT OR UPDATE ON products
FOR EACH ROW
EXECUTE FUNCTION auto_generate_embedding();
```

---

## Option 2: Scheduled Background Job (SIMPLER)

**How it works:**
1. Cron job runs every N minutes
2. Finds products with NULL embeddings
3. Generates embeddings in batch

**Pros:**
- Simpler setup
- Batch processing (cheaper)
- No Edge Functions needed

**Cons:**
- Not real-time (delay of N minutes)
- Requires external server/cron

**Setup:**

### 1. Create Python script

```python
# scripts/cron/auto_generate_embeddings.py
"""
Auto-generate embeddings for products with NULL embeddings
Run this every 5-10 minutes via cron
"""

import os
import psycopg2
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def generate_missing_embeddings():
    conn = psycopg2.connect(
        host=os.getenv('SUPABASE_HOST'),
        database=os.getenv('SUPABASE_DATABASE'),
        user=os.getenv('SUPABASE_USER'),
        password=os.getenv('SUPABASE_PASSWORD'),
        port=int(os.getenv('SUPABASE_PORT', '5432'))
    )
    cur = conn.cursor()

    # Find products needing embeddings (limit 100 per run)
    cur.execute("""
        SELECT product_id_internal, embedding_text
        FROM products
        WHERE embedding IS NULL AND embedding_text IS NOT NULL
        LIMIT 100
    """)

    products = cur.fetchall()

    if not products:
        print("No products need embeddings")
        return

    # Generate embeddings in batch
    texts = [p[1] for p in products]
    response = client.embeddings.create(
        input=texts,
        model="text-embedding-3-small"
    )

    embeddings = [item.embedding for item in response.data]

    # Update database
    for (product_id, _), embedding in zip(products, embeddings):
        cur.execute("""
            UPDATE products
            SET embedding = %s::vector
            WHERE product_id_internal = %s
        """, (embedding, product_id))

    conn.commit()
    print(f"Generated {len(products)} embeddings")

    cur.close()
    conn.close()

if __name__ == "__main__":
    generate_missing_embeddings()
```

### 2. Setup Cron Job

```bash
# Run every 10 minutes
*/10 * * * * cd /path/to/sole-backend && source .venv/bin/activate && python scripts/cron/auto_generate_embeddings.py >> logs/cron.log 2>&1
```

---

## Option 3: Supabase pg_cron Extension (BEST FOR SUPABASE)

**How it works:**
1. Use Supabase's built-in `pg_cron` extension
2. Schedule SQL function to run periodically
3. Function calls http extension to hit OpenAI API

**Pros:**
- Native to Supabase
- No external infrastructure
- Fully automated

**Cons:**
- Requires http extension
- More complex SQL

**Setup:**

```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS http;

-- Function to generate embeddings in batch
CREATE OR REPLACE FUNCTION cron_generate_embeddings()
RETURNS void AS $$
DECLARE
  product_record RECORD;
  embedding_response TEXT;
  embedding_vector vector(1536);
  api_key TEXT;
  api_url TEXT;
BEGIN
  -- Get API key from Vault
  SELECT decrypted_secret INTO api_key
  FROM vault.decrypted_secrets
  WHERE name = 'openrouter_api_key';  -- or 'openai_api_key'

  -- Set API URL (OpenRouter or OpenAI)
  api_url := 'https://openrouter.ai/api/v1/embeddings';  -- or https://api.openai.com/v1/embeddings

  -- Process up to 100 products per run
  FOR product_record IN
    SELECT product_id_internal, embedding_text
    FROM products
    WHERE embedding IS NULL AND embedding_text IS NOT NULL
    LIMIT 100
  LOOP
    -- Call OpenRouter/OpenAI API
    SELECT content INTO embedding_response
    FROM http((
      'POST',
      api_url,
      ARRAY[
        http_header('Authorization', 'Bearer ' || api_key),
        http_header('Content-Type', 'application/json')
      ],
      'application/json',
      json_build_object(
        'model', 'openai/text-embedding-3-small',  -- OpenRouter format (remove 'openai/' for direct OpenAI)
        'input', product_record.embedding_text
      )::text
    ));

    -- Extract embedding from response
    embedding_vector := (embedding_response::json->'data'->0->>'embedding')::vector;

    -- Update product
    UPDATE products
    SET embedding = embedding_vector
    WHERE product_id_internal = product_record.product_id_internal;
  END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Schedule to run every 10 minutes
SELECT cron.schedule(
  'generate-embeddings',
  '*/10 * * * *',
  'SELECT cron_generate_embeddings()'
);
```

---

## Recommendation

**For now:** Use the manual migration script (master_migration_fresh.py)

**For future:** Set up **Option 2 (Cron Job)** - it's the simplest and most reliable:
1. Easy to debug
2. Works with your existing Python setup
3. No Supabase config changes needed
4. Can run on your local machine or any server

**Later:** Migrate to **Option 3 (pg_cron)** when you want fully automated Supabase-native solution
