-- Demo ADMIN content for the admin-dashboard training scenarios.
-- The admin walkthroughs perform REAL actions (approve an application, moderate a review,
-- create announcements/expos/itineraries), which consume/accumulate data. This script
-- RESETS the demo org (id=7) to a known state and SEEDS the items those scenarios need, so
-- every recording run starts clean and reproducible. Run it BEFORE each mutating admin run:
--
--   psql "$DATABASE_URL" -f scripts/seed_demo_admin_data.sql
--
-- Idempotent + demo-scoped: it only touches org_id=7 rows tagged with our sentinels
-- (contact/reviewer email '%@demo.local'; announcement/expo titles 'TG Demo%'; itinerary
-- slugs 'tg-demo-%'), so it never duplicates and never clobbers real data. No Tourism_API
-- code change — data only.

BEGIN;

-- 1) Clean prior demo-seeded + scenario-created rows (clean slate) -------------------------
-- A member created by a previous approval of the seeded application (sentinel email):
DELETE FROM members
  WHERE organization_id = 7 AND email LIKE '%@demo.local' AND COALESCE(is_demo, false) = false;
DELETE FROM member_applications WHERE organization_id = 7 AND contact_email LIKE '%@demo.local';
DELETE FROM member_reviews
  WHERE reviewer_email LIKE '%@demo.local'
    AND member_slug IN (SELECT slug FROM members WHERE organization_id = 7);
DELETE FROM platform_announcements WHERE organization_id = 7 AND title LIKE 'TG Demo%';
DELETE FROM expo_events            WHERE organization_id = 7 AND name  LIKE 'TG Demo%';
DELETE FROM itinerary_templates    WHERE organization_id = 7 AND slug  LIKE 'tg-demo-%';

-- 2) Seed a PENDING partner application (admin-applications approves/denies it) -------------
INSERT INTO member_applications
  (business_name, business_type, contact_email, contact_phone, city, region,
   description, applicant_message, price_range, latitude, longitude,
   status, organization_id, locale, created_at)
VALUES
  ('TG Demo Wellness Spa', 'hotel', 'spa@demo.local', '+359 888 000 004', 'Bansko', 'Bansko',
   'A boutique spa and wellness retreat applying to join the platform.',
   'We would love to reach European travellers through Wonderful Bulgaria.',
   '€€', 41.8367, 23.4884,                 -- coords required to approve (creates a member)
   'pending', 7, 'en', now());

-- 3) Seed a PENDING review (admin-reviews approves/rejects it) ------------------------------
INSERT INTO member_reviews
  (member_slug, reviewer_name, reviewer_country, reviewer_email, rating, title, review_text,
   status, created_at)
VALUES
  ('demo-hotel', 'TG Demo Guest', 'FR', 'guest@demo.local', 4,
   'Lovely seaside stay, awaiting moderation',
   'A pleasant visit with friendly staff — this review is pending approval.',
   'pending', now());

-- 4) Sample announcement / expo / itinerary so the LIST sections are populated even before
--    the create scenarios run (and as edit targets). Sentinel-tagged for clean re-seed. -----
INSERT INTO platform_announcements
  (type, title, body, priority, organization_id, is_active, created_at)
VALUES
  ('team_communication', 'TG Demo Welcome',
   'Sample announcement used by the admin tutorials.', 1, 7, true, now());

INSERT INTO expo_events
  (name, location, description, start_date, end_date, attribution_window_hours,
   organization_id, is_active, created_at)
VALUES
  ('TG Demo Tourism Fair', 'Sofia Exhibition Center',
   'Sample expo used by the admin tutorials.',
   current_date + 30, current_date + 32, 48, 7, true, now());

INSERT INTO itinerary_templates
  (slug, title, description, duration_days, pace, interests, locations, locale, sort_order,
   organization_id, is_active, created_at)
VALUES
  ('tg-demo-wellness-3d', 'TG Demo Wellness Retreat',
   'Sample 3-day wellness itinerary used by the admin tutorials.',
   3, 'relaxed', ARRAY['spa', 'wellness'],
   '[{"name":"Bansko Spa","latitude":41.8367,"longitude":23.4884,"place_type":"spa"}]'::jsonb,
   'en', 0, 7, true, now());

-- 5) Report the known state ----------------------------------------------------------------
SELECT 'pending_application' AS seeded, count(*) FROM member_applications
   WHERE organization_id = 7 AND contact_email LIKE '%@demo.local' AND status = 'pending'
UNION ALL SELECT 'pending_review', count(*) FROM member_reviews
   WHERE reviewer_email LIKE '%@demo.local' AND status = 'pending'
UNION ALL SELECT 'announcement', count(*) FROM platform_announcements
   WHERE organization_id = 7 AND title LIKE 'TG Demo%'
UNION ALL SELECT 'expo', count(*) FROM expo_events
   WHERE organization_id = 7 AND name LIKE 'TG Demo%'
UNION ALL SELECT 'itinerary', count(*) FROM itinerary_templates
   WHERE organization_id = 7 AND slug LIKE 'tg-demo-%';

COMMIT;
