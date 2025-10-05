# Auto-Generate Embeddings on Insert/Update in Supabase

## Setup: Database Trigger + Edge Function

This will automatically:
1. Normalize product name to `embedding_text` (lowercase, cleaned)
2. Generate embedding via OpenRouter API
3. Store embedding in database

---

## Step 1: Store OpenRouter API Key in Supabase Vault

Run this in Supabase SQL Editor:

```sql
-- Store your OpenRouter API key securely
SELECT vault.create_secret('sk-or-v1-YOUR_KEY_HERE', 'openrouter_api_key');

-- Verify it's stored
SELECT name FROM vault.decrypted_secrets WHERE name = 'openrouter_api_key';
```

---

## Step 2: Create Edge Function for Embeddings

### Install Supabase CLI (if not installed):
```bash
npm install -g supabase
```

### Create the function:
```bash
cd /Users/anthonynguyen/notDesktop/Local-Projects/sole-backend
supabase functions new generate-product-embedding
```

### Edit the function file:
**File: `supabase/functions/generate-product-embedding/index.ts`**

```typescript
import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'

serve(async (req) => {
  try {
    const { product_name, style_id } = await req.json()

    // Normalize text (same logic as Python)
    function normalizeText(text: string): string {
      if (!text) return ''

      // Expand abbreviations
      text = text.replace(/\bWmns\b/gi, 'womens')
      text = text.replace(/\(W\)/gi, 'womens')

      // Remove special characters
      text = text.replace(/[()'"_-]/g, ' ')

      // Lowercase
      text = text.toLowerCase()

      // Normalize spaces
      text = text.replace(/\s+/g, ' ').trim()

      return text
    }

    // Generate embedding_text
    function generateEmbeddingText(name: string, styleId?: string): string {
      const normalizedName = normalizeText(name)

      if (styleId) {
        const normalizedStyle = styleId
          .replace(/[\s_-]/g, '')
          .replace(/\//g, ' ')
          .toLowerCase()
        return `${normalizedStyle} | ${normalizedName}`.trim()
      }

      return normalizedName
    }

    const embeddingText = generateEmbeddingText(product_name, style_id)

    // Get OpenRouter API key from environment
    const apiKey = Deno.env.get('OPENROUTER_API_KEY')

    // Call OpenRouter API for embedding
    const response = await fetch('https://openrouter.ai/api/v1/embeddings', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'openai/text-embedding-3-small',
        input: embeddingText,
      })
    })

    const data = await response.json()
    const embedding = data.data[0].embedding

    return new Response(
      JSON.stringify({
        embedding_text: embeddingText,
        embedding: embedding
      }),
      {
        headers: { 'Content-Type': 'application/json' },
        status: 200
      }
    )

  } catch (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      {
        headers: { 'Content-Type': 'application/json' },
        status: 500
      }
    )
  }
})
```

---

## Step 3: Deploy Edge Function

```bash
# Set the OpenRouter API key as a secret
supabase secrets set OPENROUTER_API_KEY=sk-or-v1-YOUR_KEY_HERE

# Deploy the function
supabase functions deploy generate-product-embedding --no-verify-jwt
```

---

## Step 4: Create Database Trigger

Run this in Supabase SQL Editor:

```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS http;

-- Function to auto-generate embedding on insert/update
CREATE OR REPLACE FUNCTION auto_generate_product_embedding()
RETURNS TRIGGER AS $$
DECLARE
  edge_function_url TEXT;
  embedding_result JSONB;
  http_response RECORD;
BEGIN
  -- Only run if embedding_text changed or embedding is NULL
  IF (TG_OP = 'INSERT' AND NEW.embedding IS NULL) OR
     (TG_OP = 'UPDATE' AND (NEW.product_name_platform != OLD.product_name_platform OR
                            NEW.style_id_platform != OLD.style_id_platform)) THEN

    -- Get your Supabase project URL
    edge_function_url := 'https://YOUR_PROJECT_REF.supabase.co/functions/v1/generate-product-embedding';

    -- Call Edge Function
    SELECT * INTO http_response FROM http((
      'POST',
      edge_function_url,
      ARRAY[http_header('Content-Type', 'application/json')],
      'application/json',
      json_build_object(
        'product_name', NEW.product_name_platform,
        'style_id', NEW.style_id_platform
      )::text
    ));

    -- Parse response
    embedding_result := http_response.content::jsonb;

    -- Update the record
    NEW.embedding_text := embedding_result->>'embedding_text';
    NEW.embedding := (embedding_result->>'embedding')::vector;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
DROP TRIGGER IF EXISTS trigger_auto_generate_product_embedding ON products;
CREATE TRIGGER trigger_auto_generate_product_embedding
  BEFORE INSERT OR UPDATE ON products
  FOR EACH ROW
  EXECUTE FUNCTION auto_generate_product_embedding();
```

**Replace `YOUR_PROJECT_REF` with your actual Supabase project reference.**

---

## Step 5: Test It

Insert a product and it should auto-generate embedding:

```sql
INSERT INTO products (
  product_id_platform,
  platform,
  product_name_platform,
  style_id_platform
) VALUES (
  'test-123',
  'stockx',
  'Air Jordan 1 Retro High OG (Women''s)',
  'DD0385-100'
);

-- Check the result
SELECT
  product_name_platform,
  style_id_platform,
  embedding_text,
  embedding IS NOT NULL as has_embedding
FROM products
WHERE product_id_platform = 'test-123';
```

Expected result:
- `embedding_text`: `"dd0385100 | air jordan 1 retro high og womens"`
- `has_embedding`: `true`

---

## Cost

**OpenRouter pricing for `text-embedding-3-small`:**
- Same as OpenAI: $0.02 per 1M tokens
- Each product ~10 tokens
- 461K products = ~$9.20 total

**But triggers cost on EVERY insert/update**, so:
- Use this for **new products only** going forward
- For bulk migrations, use the Batch API script

---

## Disable Trigger (for bulk operations)

```sql
-- Disable trigger temporarily for bulk inserts
ALTER TABLE products DISABLE TRIGGER trigger_auto_generate_product_embedding;

-- Re-enable after bulk operation
ALTER TABLE products ENABLE TRIGGER trigger_auto_generate_product_embedding;
```

---

## Troubleshooting

**Trigger not working?**
1. Check Edge Function logs in Supabase dashboard
2. Verify API key is set: `supabase secrets list`
3. Check trigger exists: `\d products` in SQL editor

**Too slow?**
- Triggers run synchronously (blocks INSERT)
- For bulk operations, disable trigger and use Batch API script
