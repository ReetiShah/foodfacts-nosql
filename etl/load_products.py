"""Stream the Open Food Facts JSONL export, clean it, and upsert into MongoDB."""
import argparse, gzip, json, time
from datetime import datetime, timezone
from pymongo import MongoClient, ReplaceOne
from tqdm import tqdm

NUTRIENTS = ['energy-kcal_100g', 'fat_100g', 'saturated-fat_100g', 'sugars_100g',
             'salt_100g', 'fiber_100g', 'proteins_100g']
GRADES = {'a', 'b', 'c', 'd', 'e'}


def to_float(v):
    try:
        f = float(v)
        return f if 0 <= f <= 1000 else None   # drop negative or absurd values
    except (TypeError, ValueError):
        return None


def to_date(ts):
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def clean(p):
    code = str(p.get('code') or '').strip()
    name = (p.get('product_name') or '').strip()
    countries = p.get('countries_tags') or []
    if not code or not name or not countries:
        return None, 'missing_core'

    raw_n = p.get('nutriments') or {}
    nutr = {k.replace('-', '_'): to_float(raw_n.get(k)) for k in NUTRIENTS}
    nutr = {k: v for k, v in nutr.items() if v is not None}
    if len(nutr) < 4:
        return None, 'sparse_nutrition'

    nova = str(p.get('nova_group'))
    nutri = (p.get('nutriscore_grade') or '').lower()
    eco = (p.get('ecoscore_grade') or p.get('environmental_score_grade') or '').lower()
    ingredients = [i for i in (p.get('ingredients') or []) if isinstance(i, dict) and i.get('id')]

    doc = {
        '_id': code,
        'code': code,
        'product_name': name[:200],
        'brands_tags': p.get('brands_tags'),
        'categories_tags': p.get('categories_tags'),
        'pnns_groups_1': p.get('pnns_groups_1'),
        'pnns_groups_2': p.get('pnns_groups_2'),
        'countries_tags': countries,
        'labels_tags': p.get('labels_tags'),
        'allergens_tags': p.get('allergens_tags'),
        'additives_tags': p.get('additives_tags'),
        'additives_n': len(p.get('additives_tags') or []),
        'ingredients': [{'id': i['id'],
                         'percent_estimate': i.get('percent_estimate'),
                         'vegan': i.get('vegan')} for i in ingredients[:40]],
        'ingredients_n': len(ingredients),
        'nutriments': nutr,
        'nova_group': int(nova) if nova in {'1', '2', '3', '4'} else None,
        'nutriscore_grade': nutri if nutri in GRADES else None,
        'ecoscore_grade': eco if eco in GRADES else None,
        'completeness': p.get('completeness'),
        'created_at': to_date(p.get('created_t')),
    }
    return {k: v for k, v in doc.items() if v not in (None, [], {}, '')}, 'ok'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='data/openfoodfacts-products.jsonl.gz')
    ap.add_argument('--uri', default='mongodb://localhost:27017')
    ap.add_argument('--db', default='foodfacts')
    ap.add_argument('--limit', type=int, default=500_000, help='max clean docs to load')
    ap.add_argument('--batch', type=int, default=2000)
    args = ap.parse_args()

    db = MongoClient(args.uri)[args.db]
    coll = db['products']
    stats, ops, loaded, start = {}, [], 0, time.time()

    with gzip.open(args.file, 'rt', encoding='utf-8') as f:
        for line in tqdm(f, unit=' lines'):
            try:
                doc, reason = clean(json.loads(line))
            except json.JSONDecodeError:
                doc, reason = None, 'bad_json'
            stats[reason] = stats.get(reason, 0) + 1
            if doc is None:
                continue
            ops.append(ReplaceOne({'code': doc['code']}, doc, upsert=True))
            loaded += 1
            if len(ops) >= args.batch:
                coll.bulk_write(ops, ordered=False)
                ops = []
            if loaded >= args.limit:
                break
    if ops:
        coll.bulk_write(ops, ordered=False)

    secs = time.time() - start
    print(f'Loaded {loaded:,} docs in {secs:,.0f}s ({loaded / secs:,.0f} docs/s)')
    print('Line outcomes:', stats)
    db['etl_runs'].insert_one({'at': datetime.now(timezone.utc), 'file': args.file,
                               'loaded': loaded, 'seconds': secs, 'stats': stats})


if __name__ == '__main__':
    main()
