import json, os, time
import redis
from fastapi import FastAPI
from pymongo import MongoClient
import substitutes

db = MongoClient(os.getenv('MONGO_URI', 'mongodb://localhost:27017'))['foodfacts']
substitutes.db = db
cache = redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'), decode_responses=True)
app = FastAPI(title='Food Facts API', description='Analytics on US packaged foods (MongoDB + Redis)')
UPF = {'$cond': [{'$eq': ['$nova_group', 4]}, 1, 0]}


def cached(key, ttl, compute):
    t = time.perf_counter()
    hit = cache.get(key)
    if hit:
        data, source = json.loads(hit), 'redis'
    else:
        data, source = compute(), 'mongodb'
        cache.setex(key, ttl, json.dumps(data, default=str))
    return {'source': source, 'ms': round((time.perf_counter() - t) * 1000, 1), 'data': data}


@app.get('/stats/upf-by-food-group')
def upf_by_food_group(min_products: int = 200):
    pipeline = [
        {'$match': {'nova_group': {'$exists': True}, 'pnns_groups_2': {'$ne': 'unknown'}}},
        {'$group': {'_id': '$pnns_groups_2', 'products': {'$sum': 1}, 'upf': {'$sum': UPF}}},
        {'$match': {'products': {'$gte': min_products}}},
        {'$project': {'products': 1, 'upf_pct': {'$round': [{'$multiply': [{'$divide': ['$upf', '$products']}, 100]}, 1]}}},
        {'$sort': {'upf_pct': -1}},
    ]
    return cached(f'upf:{min_products}', 3600, lambda: list(db.products.aggregate(pipeline)))


@app.get('/brands/{brand}')
def brand(brand: str):
    return db.brand_scorecards.find_one({'_id': brand}) or {'error': 'brand not found'}


@app.get('/substitutes/{code}')
def find_substitutes(code: str, avoid: str | None = None):
    return cached(f'sub:{code}:{avoid}', 600, lambda: substitutes.substitutes(code, avoid))
