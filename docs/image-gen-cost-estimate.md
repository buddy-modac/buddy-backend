# Image Generation Cost Estimate

## Summary

- Model matrix subtotal: **$0.5806**
- All real image runs subtotal: **$0.9143**
- OpenAI organization costs API check failed with missing `api.usage.read` scope, so this is a usage-token-based estimate from saved API responses.

## By Run Group

| Group | Estimated cost |
| --- | ---: |
| Model matrix 9 runs | $0.5806 |
| Basic real 3 runs | $0.1321 |
| Article real 3 runs | $0.2017 |

## By Model

| Model | Estimated cost |
| --- | ---: |
| gpt-image-1 | $0.5353 |
| gpt-image-1.5 | $0.2245 |
| gpt-image-2 | $0.1545 |

## Per Run

| Group | Case | Model | Action | Text input tokens | Image input tokens | Output tokens | Estimated cost |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| Model matrix 9 runs | medium-article-image-change | gpt-image-1 | edit-image | 114 | 452 | 1584 | $0.0672 |
| Model matrix 9 runs | medium-article-image-change | gpt-image-1.5 | edit-image | 114 | 452 | 2146 | $0.0729 |
| Model matrix 9 runs | medium-article-image-change | gpt-image-2 | edit-image | 77 | 1242 | 1372 | $0.0515 |
| Model matrix 9 runs | medium-article-speech-bubble | gpt-image-1 | edit-image | 120 | 452 | 1584 | $0.0672 |
| Model matrix 9 runs | medium-article-speech-bubble | gpt-image-1.5 | edit-image | 120 | 452 | 2124 | $0.0722 |
| Model matrix 9 runs | medium-article-speech-bubble | gpt-image-2 | edit-image | 83 | 1242 | 1372 | $0.0515 |
| Model matrix 9 runs | medium-article-translate-ko | gpt-image-1 | translate-text | 110 | 452 | 1584 | $0.0672 |
| Model matrix 9 runs | medium-article-translate-ko | gpt-image-1.5 | translate-text | 110 | 452 | 2354 | $0.0795 |
| Model matrix 9 runs | medium-article-translate-ko | gpt-image-2 | translate-text | 73 | 1242 | 1372 | $0.0515 |
| Basic real 3 runs | buddy-image-edit | gpt-image-1 | edit-image | 79 | 323 | 1056 | $0.0450 |
| Basic real 3 runs | buddy-simple-generate | gpt-image-1 | generate | 40 | 0 | 1056 | $0.0422 |
| Basic real 3 runs | buddy-translate-text-edit | gpt-image-1 | translate-text | 71 | 323 | 1056 | $0.0449 |
| Article real 3 runs | medium-article-content-rewrite | gpt-image-1 | edit-image | 137 | 452 | 1584 | $0.0673 |
| Article real 3 runs | medium-article-image-change | gpt-image-1 | edit-image | 114 | 452 | 1584 | $0.0672 |
| Article real 3 runs | medium-article-translate-ko | gpt-image-1 | translate-text | 110 | 452 | 1584 | $0.0672 |

## Pricing Assumptions

- `gpt-image-1.5`: text input $5 / 1M tokens, image input $8 / 1M tokens, output $32 / 1M tokens.
- `gpt-image-2`: text input $5 / 1M tokens, image input $8 / 1M tokens, output $30 / 1M tokens.
- `gpt-image-1`: output estimated from official guide 1024x1536 medium image price $0.063 and 1584 output tokens; input estimated with the same current image-model input rates because current pricing page does not list `gpt-image-1` separately.
