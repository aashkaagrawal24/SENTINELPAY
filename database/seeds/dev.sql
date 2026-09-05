-- Run after creating an auth user; replace the single UUID below with that user's auth.users id.
\set demo_user_id '00000000-0000-0000-0000-000000000001'
insert into public.profiles(id,display_name) values(:'demo_user_id','Demo Merchant Owner') on conflict do nothing;
insert into public.merchants(id,name) values('10000000-0000-0000-0000-000000000001','Sentinel Audio Demo') on conflict do nothing;
insert into public.merchant_users(merchant_id,user_id,role) values('10000000-0000-0000-0000-000000000001',:'demo_user_id','OWNER') on conflict do nothing;
insert into public.merchant_products(id,merchant_id,sku,name,brand,category,description,base_price_minor,metadata) values
('20000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','SONY-XM4','Sony WH-1000XM4','Sony','Headphones','Premium noise-cancelling headphones',1999900,'{"warranty":"1 year","returns":"7 days"}'),
('20000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001','SONY-XM5','Sony WH-1000XM5','Sony','Headphones','Flagship noise-cancelling headphones',2449900,'{"warranty":"1 year","returns":"7 days"}'),
('20000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000001','CASE-XM','Protective Case','Sentinel','Accessories','Protective travel case',49900,'{"returns":"7 days"}') on conflict do nothing;
insert into public.product_variants(product_id,variant_key,name,attributes) values
('20000000-0000-0000-0000-000000000001','black','Black','{"color":"black"}'),('20000000-0000-0000-0000-000000000002','silver','Silver','{"color":"silver"}'),('20000000-0000-0000-0000-000000000003','standard','Standard','{"size":"standard"}') on conflict do nothing;
insert into public.merchant_inventory(merchant_id,product_id,available_quantity) values
('10000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001',20),('10000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000002',12),('10000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000003',50) on conflict do nothing;
insert into public.merchant_policies(merchant_id,scope,scope_reference,base_price_minor,minimum_sale_price_minor,maximum_discount_percent,negotiation_enabled,max_negotiation_rounds,cross_sell_enabled,status,version) values('10000000-0000-0000-0000-000000000001','PRODUCT','20000000-0000-0000-0000-000000000001',1999900,1850000,7.50,true,3,true,'ACTIVE',1) on conflict do nothing;
insert into public.merchant_relationships(merchant_id,source_product_id,target_product_id,relationship_type,priority) values('10000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000003','ACCESSORY',10),('10000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000002','UPSELL',5) on conflict do nothing;
