from pymongo import MongoClient

db = MongoClient('mongodb://localhost:27017')['foodfacts']   # replaced by main.py
GRADES = ['a', 'b', 'c', 'd', 'e']
FIELDS = ('sugars_100g', 'fat_100g', 'salt_100g', 'proteins_100g')


def substitutes(code, avoid_allergen=None, k=5):
    p = db.products.find_one({'code': code})
    if not p or 'pnns_groups_2' not in p or 'nutriscore_grade' not in p:
        return []
    better = GRADES[:GRADES.index(p['nutriscore_grade'])] or ['a']
    match = {'pnns_groups_2': p['pnns_groups_2'], 'nutriscore_grade': {'$in': better},
             'code': {'$ne': code}}
    if avoid_allergen:
        match['allergens_tags'] = {'$ne': avoid_allergen}
    distance = {'$add': [
        {'$abs': {'$subtract': [{'$ifNull': [f'$nutriments.{f}', 0]},
                                p['nutriments'].get(f, 0)]}} for f in FIELDS]}
    pipeline = [
        {'$match': match},
        {'$set': {'distance': distance}},
        {'$sort': {'distance': 1}},
        {'$limit': k},
        {'$project': {'_id': 0, 'code': 1, 'product_name': 1, 'nutriscore_grade': 1,
                      'nova_group': 1, 'distance': {'$round': ['$distance', 1]}}},
    ]
    return list(db.products.aggregate(pipeline))
