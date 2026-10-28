db = db.getSiblingDB('foodfacts');

const pct = (part, whole) => ({ $round: [{ $multiply: [{ $divide: [part, whole] }, 100] }, 1] });
const isUPF = { $cond: [{ $eq: ['$nova_group', 4] }, 1, 0] };
const score = { $indexOfArray: [['a', 'b', 'c', 'd', 'e'], '$nutriscore_grade'] };
const show = (title, pipeline) => {
  const t = Date.now();
  const rows = db.products.aggregate(pipeline, { allowDiskUse: true }).toArray();
  print(`\n=== ${title}  (${Date.now() - t} ms) ===`);
  rows.forEach(r => printjson(r));
};

show('Q1 Ultra-processed share by food group', [
  { $match: { nova_group: { $exists: true }, pnns_groups_2: { $ne: 'unknown' } } },
  { $group: { _id: '$pnns_groups_2', products: { $sum: 1 }, upf: { $sum: isUPF } } },
  { $match: { products: { $gte: 200 } } },
  { $project: { products: 1, upf_pct: pct('$upf', '$products') } },
  { $sort: { upf_pct: -1 } }
]);

show('Q2-prep Most common labels', [
  { $unwind: '$labels_tags' },
  { $group: { _id: '$labels_tags', products: { $sum: 1 } } },
  { $sort: { products: -1 } },
  { $limit: 15 }
]);

const halo = ['en:organic', 'en:usda-organic', 'en:non-gmo-project', 'en:no-gmos', 'en:vegan',
              'en:no-gluten', 'en:no-added-sugar', 'en:no-preservatives',
              'en:no-artificial-flavors', 'en:100-natural'];
show('Q2 Health-halo labels vs Nutri-Score and NOVA', [
  { $match: { labels_tags: { $in: halo }, nutriscore_grade: { $exists: true }, nova_group: { $exists: true } } },
  { $unwind: '$labels_tags' },
  { $match: { labels_tags: { $in: halo } } },
  { $group: { _id: '$labels_tags', products: { $sum: 1 },
      poor: { $sum: { $cond: [{ $in: ['$nutriscore_grade', ['d', 'e']] }, 1, 0] } },
      upf: { $sum: isUPF } } },
  { $project: { products: 1, pct_grade_D_or_E: pct('$poor', '$products'), pct_ultra_processed: pct('$upf', '$products') } },
  { $sort: { pct_grade_D_or_E: -1 } }
]);
show('Q2 baseline: all products', [
  { $match: { nutriscore_grade: { $exists: true }, nova_group: { $exists: true } } },
  { $group: { _id: 'all products', products: { $sum: 1 },
      poor: { $sum: { $cond: [{ $in: ['$nutriscore_grade', ['d', 'e']] }, 1, 0] } },
      upf: { $sum: isUPF } } },
  { $project: { products: 1, pct_grade_D_or_E: pct('$poor', '$products'), pct_ultra_processed: pct('$upf', '$products') } }
]);

show('Q3 Top additives and their link to ultra-processing', [
  { $match: { additives_n: { $gt: 0 }, nova_group: { $exists: true } } },
  { $unwind: '$additives_tags' },
  { $group: { _id: '$additives_tags', products: { $sum: 1 }, upf: { $sum: isUPF } } },
  { $sort: { products: -1 } },
  { $limit: 20 },
  { $lookup: { from: 'additives_ref', localField: '_id', foreignField: '_id', as: 'ref' } },
  { $project: { products: 1, upf_pct: pct('$upf', '$products'), name: { $first: '$ref.name' }, role: { $first: '$ref.role' } } }
]);

show('Q4 Brand leaderboard (brands with 50+ graded products)', [
  { $match: { nutriscore_grade: { $exists: true }, brands_tags: { $exists: true } } },
  { $unwind: '$brands_tags' },
  { $group: { _id: '$brands_tags', products: { $sum: 1 }, avg_score: { $avg: score } } },
  { $match: { products: { $gte: 50 } } },
  { $set: { avg_score: { $round: ['$avg_score', 2] } } },
  { $facet: {
      healthiest: [{ $sort: { avg_score: 1 } }, { $limit: 10 }],
      least_healthy: [{ $sort: { avg_score: -1 } }, { $limit: 10 }] } }
]);

show('Q5 Nutri-Score vs Eco-Score', [
  { $match: { nutriscore_grade: { $exists: true }, ecoscore_grade: { $exists: true } } },
  { $facet: {
      matrix: [
        { $group: { _id: { nutri: '$nutriscore_grade', eco: '$ecoscore_grade' }, n: { $sum: 1 } } },
        { $sort: { '_id.nutri': 1, '_id.eco': 1 } } ],
      agreement: [
        { $group: { _id: null, total: { $sum: 1 },
            same: { $sum: { $cond: [{ $eq: ['$nutriscore_grade', '$ecoscore_grade'] }, 1, 0] } } } },
        { $project: { _id: 0, total: 1, same_grade_pct: pct('$same', '$total') } } ] } }
]);

show('Q6 Products added per year (data provenance)', [
  { $match: { created_at: { $exists: true } } },
  { $group: { _id: { $year: '$created_at' }, added: { $sum: 1 } } },
  { $setWindowFields: { sortBy: { _id: 1 }, output: {
      running_total: { $sum: '$added', window: { documents: ['unbounded', 'current'] } } } } },
  { $sort: { _id: 1 } }
]);

show('Q7a Sugar bands per 100 g: low <5, medium 5-22.5, high >22.5', [
  { $match: { 'nutriments.sugars_100g': { $gte: 0, $lte: 100 }, nova_group: { $exists: true } } },
  { $bucket: { groupBy: '$nutriments.sugars_100g', boundaries: [0, 5, 22.5, 100.01],
      output: { products: { $sum: 1 }, upf_pct: { $avg: { $multiply: [isUPF, 100] } } } } },
  { $set: { upf_pct: { $round: ['$upf_pct', 1] } } }
]);
show('Q7b Median sugar by food group', [
  { $match: { pnns_groups_2: { $ne: 'unknown' }, 'nutriments.sugars_100g': { $lte: 100 } } },
  { $group: { _id: '$pnns_groups_2', products: { $sum: 1 },
      median_sugar: { $median: { input: '$nutriments.sugars_100g', method: 'approximate' } } } },
  { $match: { products: { $gte: 200 } } },
  { $set: { median_sugar: { $round: ['$median_sugar', 1] } } },
  { $sort: { median_sugar: -1 } }
]);

show('Q8 Ingredient and additive counts by NOVA group', [
  { $match: { nova_group: { $exists: true }, ingredients_n: { $gt: 0 } } },
  { $group: { _id: '$nova_group', products: { $sum: 1 },
      avg_ingredients: { $avg: '$ingredients_n' }, avg_additives: { $avg: '$additives_n' } } },
  { $set: { avg_ingredients: { $round: ['$avg_ingredients', 1] }, avg_additives: { $round: ['$avg_additives', 2] } } },
  { $sort: { _id: 1 } }
]);

show('Q10 "protein bar" products by Nutri-Score', [
  { $match: { $text: { $search: '"protein bar"' }, nutriscore_grade: { $exists: true } } },
  { $group: { _id: '$nutriscore_grade', products: { $sum: 1 } } },
  { $sort: { _id: 1 } }
]);

show('Q12 Organic vs non-organic within the same food group (positive gap = organic healthier)', [
  { $match: { pnns_groups_2: { $ne: 'unknown' }, nutriscore_grade: { $exists: true }, nova_group: { $exists: true } } },
  { $set: { organic: { $in: ['en:organic', { $ifNull: ['$labels_tags', []] }] } } },
  { $group: { _id: '$pnns_groups_2',
      org_n: { $sum: { $cond: ['$organic', 1, 0] } },
      org_score: { $sum: { $cond: ['$organic', score, 0] } },
      org_upf: { $sum: { $cond: ['$organic', isUPF, 0] } },
      other_n: { $sum: { $cond: ['$organic', 0, 1] } },
      other_score: { $sum: { $cond: ['$organic', 0, score] } },
      other_upf: { $sum: { $cond: ['$organic', 0, isUPF] } } } },
  { $match: { org_n: { $gte: 30 }, other_n: { $gte: 30 } } },
  { $project: { organic_products: '$org_n', other_products: '$other_n',
      organic_avg_score: { $round: [{ $divide: ['$org_score', '$org_n'] }, 2] },
      other_avg_score: { $round: [{ $divide: ['$other_score', '$other_n'] }, 2] },
      organic_upf_pct: pct('$org_upf', '$org_n'),
      other_upf_pct: pct('$other_upf', '$other_n') } },
  { $set: { score_gap: { $round: [{ $subtract: ['$other_avg_score', '$organic_avg_score'] }, 2] } } },
  { $sort: { score_gap: -1 } }
]);

db.products.aggregate([
  { $match: { brands_tags: { $exists: true }, nutriscore_grade: { $exists: true } } },
  { $unwind: '$brands_tags' },
  { $group: { _id: '$brands_tags', products: { $sum: 1 }, avg_score: { $avg: score },
              upf: { $sum: isUPF }, avg_sugar: { $avg: '$nutriments.sugars_100g' } } },
  { $match: { products: { $gte: 20 } } },
  { $set: { upf_pct: pct('$upf', '$products'), updated_at: '$$NOW' } },
  { $merge: { into: 'brand_scorecards', whenMatched: 'replace', whenNotMatched: 'insert' } }
]);
print('\n=== Q11 brand_scorecards documents:', db.brand_scorecards.countDocuments(), '===');
