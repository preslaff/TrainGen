-- Demo member content for the member-dashboard walkthroughs (reviews + bookings).
-- The platform's seed_demo_tenants.py seeds offerings/events/reviews/clicks but NOT
-- booking_requests, and a clean tenant may have no reviews — so the member-reviews and
-- member-bookings walkthroughs would record an empty section. This adds a few rows for the
-- demo member so those videos look populated.
--
-- Data-only; touches the DEMO tenant member (demo-hotel) only. Idempotent: re-running first
-- clears its own prior rows via the `@demo.local` sentinel, so it never duplicates or clobbers
-- real data. Run after the platform seed and after any demo-tenant reset:
--
--   psql "$DATABASE_URL" -f scripts/seed_demo_member_data.sql
--
-- (DATABASE_URL is the platform DB, e.g. postgresql://…@localhost:5432/tourism_db)

BEGIN;

DELETE FROM member_reviews   WHERE member_slug='demo-hotel' AND reviewer_email LIKE '%@demo.local';
DELETE FROM booking_requests WHERE member_slug='demo-hotel' AND guest_email   LIKE '%@demo.local';

INSERT INTO member_reviews
  (member_slug, reviewer_name, reviewer_country, reviewer_email, rating, title, review_text,
   visit_date, review_date, location_rating, service_rating, value_rating, cleanliness_rating,
   helpful_count, is_verified, language, status, created_at)
VALUES
  ('demo-hotel','Alex Demo','DE','alex@demo.local',5,'Wonderful seaside stay',
   'Spotless rooms, warm staff and a perfect beachfront location. Will return.',
   now()::date - 20, now() - interval '20 days',5,5,4,5,3,true,'en','approved', now() - interval '20 days'),
  ('demo-hotel','Maria Ivanova','BG','maria@demo.local',4,'Great location, lovely breakfast',
   'Уютен хотел на първа линия с страхотна закуска и любезен персонал.',
   now()::date - 12, now() - interval '12 days',5,4,4,4,1,true,'bg','approved', now() - interval '12 days'),
  ('demo-hotel','Tom Becker','GB','tom@demo.local',5,'Best value on the coast',
   'Excellent value for money. The sea view from our balcony was unforgettable.',
   now()::date - 5, now() - interval '5 days',5,5,5,4,2,true,'en','approved', now() - interval '5 days');

INSERT INTO booking_requests
  (request_id, member_slug, offering_id, booking_type, check_in_date, check_out_date,
   party_size, nights, guest_name, guest_email, guest_phone, guest_country,
   special_requests, estimated_price, currency, status, created_at)
VALUES
  (gen_random_uuid(),'demo-hotel',NULL,'accommodation', now()::date + 14, now()::date + 17,
   2,3,'Sophie Laurent','sophie@demo.local','+33 6 12 34 56 78','FR',
   'Late check-in around 22:00, high floor if possible.',360.00,'EUR','pending', now() - interval '2 days'),
  (gen_random_uuid(),'demo-hotel',NULL,'accommodation', now()::date + 30, now()::date + 33,
   4,3,'The Petrov Family','petrov@demo.local','+359 88 765 4321','BG',
   'Two adjoining rooms, cot for an infant.',720.00,'EUR','pending', now() - interval '1 days'),
  (gen_random_uuid(),'demo-hotel',NULL,'accommodation', now()::date + 7, now()::date + 9,
   2,2,'James Wright','james@demo.local','+44 7700 900123','GB',
   'Anniversary trip — a sea-view room would be wonderful.',240.00,'EUR','confirmed', now() - interval '4 days');

COMMIT;
