"""Export fully graded products from MongoDB into CSV files for Neo4j."""
import argparse, csv, hashlib, os
from pymongo import MongoClient

NUTR = {'sugars': 'sugars_100g', 'fat': 'fat_100g', 'satfat': 'saturated_fat_100g',
        'salt': 'salt_100g', 'fiber': 'fiber_100g', 'proteins': 'proteins_100g',
        'kcal': 'energy_kcal_100g'}
REL_FILES = {   # file name -> (target column, MongoDB array field)
    'product_brand':    ('brand', 'brands_tags'),
    'product_additive': ('additive', 'additives_tags'),
    'product_allergen': ('allergen', 'allergens_tags'),
    'product_label':    ('label', 'labels_tags'),
    'product_country':  ('country', 'countries_tags'),
}


def shard_of(code):
    # Same idea as MongoDB's hashed shard key: hash the barcode, split into two partitions
    return int(hashlib.md5(code.encode()).hexdigest(), 16) % 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--uri', default='mongodb://localhost:27017')
    ap.add_argument('--size', type=int, default=0, help='0 = all graded products, N = random sample of N')
    ap.add_argument('--out', default='graph/import')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    db = MongoClient(args.uri)['foodfacts']

    files, writers = {}, {}

    def writer(name, header):
        f = open(os.path.join(args.out, f'{name}.csv'), 'w', newline='', encoding='utf-8')
        w = csv.writer(f)
        w.writerow(header)
        files[name], writers[name] = f, w
        return w

    products = writer('products', ['code', 'name', 'nova', 'nutriscore', 'ecoscore', *NUTR,
                                   'additives_n', 'ingredients_n', 'subgroup', 'shard'])
    contains = writer('product_ingredient', ['code', 'ingredient', 'rank', 'percent', 'vegan'])
    for name, (col, _) in REL_FILES.items():
        writer(name, ['code', col])
    groups = {}

    pipeline = [{'$match': {'nutriscore_grade': {'$exists': True}, 'nova_group': {'$exists': True},
                            'ingredients_n': {'$gte': 1},
                            'pnns_groups_2': {'$exists': True, '$nin': ['unknown', '']}}}]
    if args.size:
        pipeline.append({'$sample': {'size': args.size}})
    n = 0
    for p in db.products.aggregate(pipeline, allowDiskUse=True):
        code, nut = p['code'], p.get('nutriments', {})
        products.writerow([
            code, p['product_name'].replace('\n', ' '), p['nova_group'], p['nutriscore_grade'],
            p.get('ecoscore_grade', ''), *(nut.get(v, '') for v in NUTR.values()),
            p.get('additives_n', 0), p.get('ingredients_n', 0), p['pnns_groups_2'], shard_of(code)])
        groups[p['pnns_groups_2']] = p.get('pnns_groups_1', '')
        for rank, ing in enumerate(p.get('ingredients') or [], start=1):
            contains.writerow([code, ing['id'], rank, ing.get('percent_estimate'), ing.get('vegan')])
        for name, (_, field) in REL_FILES.items():
            for value in set(p.get(field) or []):
                writers[name].writerow([code, value])
        n += 1

    gw = writer('groups', ['subgroup', 'group'])
    for sub, top in groups.items():
        if top and top != 'unknown':
            gw.writerow([sub, top])
    aw = writer('additives', ['id', 'name', 'role'])     # the LLM-built reference collection
    for a in db.additives_ref.find():
        aw.writerow([a['_id'], a.get('name', ''), a.get('role', '')])
    for f in files.values():
        f.close()
    print(f'Exported {n:,} products to {args.out}/')


if __name__ == '__main__':
    main()
