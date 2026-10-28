"""Report figures from the local sharded cluster (full 145k-product sample)."""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from pymongo import MongoClient

db = MongoClient('mongodb://localhost:27017')['foodfacts']
OUT = 'report/figures'
os.makedirs(OUT, exist_ok=True)
UPF = {'$cond': [{'$eq': ['$nova_group', 4]}, 1, 0]}
GRADED = {'nutriscore_grade': {'$exists': True}, 'nova_group': {'$exists': True}}
RED, GREEN, GREY = '#d1495b', '#2e8b57', '#bbbbbb'
plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})


def pct(part, whole):
    return {'$multiply': [{'$divide': [part, whole]}, 100]}


# ---------- Figure 1: Q12 organic vs non-organic, per food group ----------
rows = db.products.aggregate([
    {'$match': {**GRADED, 'pnns_groups_2': {'$ne': 'unknown'}}},
    {'$set': {'organic': {'$in': ['en:organic', {'$ifNull': ['$labels_tags', []]}]}}},
    {'$group': {'_id': '$pnns_groups_2',
                'org_n': {'$sum': {'$cond': ['$organic', 1, 0]}},
                'org_upf': {'$sum': {'$cond': ['$organic', UPF, 0]}},
                'other_n': {'$sum': {'$cond': ['$organic', 0, 1]}},
                'other_upf': {'$sum': {'$cond': ['$organic', 0, UPF]}}}},
    {'$match': {'org_n': {'$gte': 30}, 'other_n': {'$gte': 30}}},
    {'$project': {'group': '$_id', 'organic': pct('$org_upf', '$org_n'),
                  'other': pct('$other_upf', '$other_n')}},
])
df = pd.DataFrame(rows).sort_values('other').reset_index(drop=True)
fig, ax = plt.subplots(figsize=(8, 7))
ax.hlines(df.index, df['organic'], df['other'], color=GREY, linewidth=2)
ax.scatter(df['other'], df.index, color=RED, s=45, label='Non-organic', zorder=3)
ax.scatter(df['organic'], df.index, color=GREEN, s=45, label='Organic', zorder=3)
ax.set_yticks(df.index)
ax.set_yticklabels(df['group'])
ax.set_xlim(0, 100)
ax.set_xlabel('% ultra-processed (NOVA 4)')
ax.set_title('Organic products are less ultra-processed in almost every food group')
ax.legend(frameon=False, loc='lower right')
fig.tight_layout()
fig.savefig(f'{OUT}/fig_q12_organic_vs_other.png', dpi=150)
plt.close(fig)

# ---------- Figure 2: Q2 health-halo labels vs the all-products baseline ----------
halo = ['en:100-natural', 'en:no-artificial-flavors', 'en:no-gluten', 'en:no-preservatives',
        'en:vegan', 'en:organic', 'en:usda-organic', 'en:non-gmo-project', 'en:no-gmos']
rows = db.products.aggregate([
    {'$match': {**GRADED, 'labels_tags': {'$in': halo}}},
    {'$unwind': '$labels_tags'},
    {'$match': {'labels_tags': {'$in': halo}}},
    {'$group': {'_id': '$labels_tags', 'n': {'$sum': 1}, 'upf': {'$sum': UPF}}},
    {'$project': {'label': {'$replaceOne': {'input': '$_id', 'find': 'en:', 'replacement': ''}},
                  'upf_pct': pct('$upf', '$n')}},
])
df = pd.DataFrame(rows).sort_values('upf_pct').reset_index(drop=True)
base = next(db.products.aggregate([
    {'$match': GRADED},
    {'$group': {'_id': None, 'n': {'$sum': 1}, 'upf': {'$sum': UPF}}}]))
base_upf = base['upf'] / base['n'] * 100
fig, ax = plt.subplots(figsize=(8, 5))
ax.barh(df['label'], df['upf_pct'], color=[RED if v > base_upf else GREEN for v in df['upf_pct']])
ax.axvline(base_upf, color='black', linestyle='--', linewidth=1)
ax.text(base_upf + 1, len(df) - 0.4, f'All products: {base_upf:.0f}%', fontsize=9)
for i, v in enumerate(df['upf_pct']):
    ax.text(v + 1, i, f'{v:.0f}%', va='center', fontsize=9)
ax.set_xlim(0, 105)
ax.set_xlabel('% ultra-processed (NOVA 4)')
ax.set_title("'Natural' claims are more ultra-processed than average; certified labels less")
fig.tight_layout()
fig.savefig(f'{OUT}/fig_q2_labels_vs_baseline.png', dpi=150)
plt.close(fig)

# ---------- Figure 3: Q6 data provenance ----------
rows = db.products.aggregate([
    {'$match': {'created_at': {'$exists': True}}},
    {'$group': {'_id': {'$year': '$created_at'}, 'n': {'$sum': 1}}},
    {'$sort': {'_id': 1}},
])
df = pd.DataFrame(rows)
share_2017 = df.loc[df['_id'] == 2017, 'n'].sum() / df['n'].sum() * 100
fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(df['_id'].astype(str), df['n'], color=['#4a6fa5' if y == 2017 else GREY for y in df['_id']])
ax.set_yscale('log')
ax.set_ylabel('Products added (log scale)')
ax.set_title(f'{share_2017:.1f}% of the sample was added in a single 2017 import')
fig.tight_layout()
fig.savefig(f'{OUT}/fig_q6_provenance.png', dpi=150)
plt.close(fig)

print('Saved:', ', '.join(sorted(os.listdir(OUT))))
