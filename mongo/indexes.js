db = db.getSiblingDB('foodfacts');
db.products.createIndex({ countries_tags: 1, nova_group: 1 });
db.products.createIndex({ labels_tags: 1 });
db.products.createIndex({ additives_tags: 1 });
db.products.createIndex({ brands_tags: 1, nutriscore_grade: 1 });
db.products.createIndex({ pnns_groups_2: 1, nutriscore_grade: 1 });
db.products.createIndex({ created_at: 1 });
db.products.createIndex({ product_name: 'text' });
printjson(db.products.getIndexes().map(i => i.name));
