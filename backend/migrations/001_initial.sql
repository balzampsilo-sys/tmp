-- ============================================================
-- Multi-tenant SRS platform: initial schema
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Tenants ──────────────────────────────────────────────────
CREATE TABLE tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    owner_id    UUID,
    settings    JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Users ─────────────────────────────────────────────────────
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id     BIGINT NOT NULL UNIQUE,
    username        TEXT,
    first_name      TEXT,
    language_code   TEXT DEFAULT 'ru',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE tenants ADD CONSTRAINT tenants_owner_fk
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL;

-- ── User ↔ Tenant membership ──────────────────────────────────
CREATE TYPE tenant_role AS ENUM ('owner', 'teacher', 'member');
CREATE TYPE subscription_status AS ENUM ('free', 'pro', 'expired');

CREATE TABLE user_tenants (
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role                tenant_role NOT NULL DEFAULT 'member',
    sub_status          subscription_status NOT NULL DEFAULT 'free',
    sub_expires_at      TIMESTAMPTZ,
    joined_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, tenant_id)
);

-- ── Decks ─────────────────────────────────────────────────────
CREATE TYPE deck_source AS ENUM ('platform', 'tenant', 'personal');

CREATE TABLE decks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID REFERENCES tenants(id) ON DELETE CASCADE,
    owner_id    UUID REFERENCES users(id) ON DELETE SET NULL,
    source      deck_source NOT NULL DEFAULT 'tenant',
    name        TEXT NOT NULL,
    description TEXT,
    language    TEXT NOT NULL DEFAULT 'en',
    cefr_level  TEXT CHECK (cefr_level IN ('A1','A2','B1','B2','C1','C2')),
    tags        TEXT[] NOT NULL DEFAULT '{}',
    is_public   BOOLEAN NOT NULL DEFAULT FALSE,
    card_count  INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX decks_tenant_idx ON decks(tenant_id);
CREATE INDEX decks_level_idx  ON decks(cefr_level);
CREATE INDEX decks_public_idx ON decks(is_public) WHERE is_public = TRUE;

-- ── Cards ─────────────────────────────────────────────────────
CREATE TYPE card_type AS ENUM ('basic', 'cloze', 'multiple_choice');

CREATE TABLE cards (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id         UUID NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    card_type       card_type NOT NULL DEFAULT 'basic',
    front           TEXT NOT NULL,
    back            TEXT NOT NULL,
    ipa             TEXT,
    pos             TEXT,             -- noun / verb / adj / adv / phrase
    cefr_level      TEXT CHECK (cefr_level IN ('A1','A2','B1','B2','C1','C2')),
    examples        JSONB NOT NULL DEFAULT '[]',
    -- [{"en": "...", "ru": "...", "source": "tatoeba"}]
    synonyms        TEXT[] NOT NULL DEFAULT '{}',
    word_forms      TEXT[] NOT NULL DEFAULT '{}',
    audio_url       TEXT,
    image_url       TEXT,
    tags            TEXT[] NOT NULL DEFAULT '{}',
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX cards_deck_idx  ON cards(deck_id);
CREATE INDEX cards_level_idx ON cards(cefr_level);

-- keep card_count in sync
CREATE OR REPLACE FUNCTION update_deck_card_count() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE decks SET card_count = card_count + 1 WHERE id = NEW.deck_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE decks SET card_count = card_count - 1 WHERE id = OLD.deck_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER cards_count_trigger
    AFTER INSERT OR DELETE ON cards
    FOR EACH ROW EXECUTE FUNCTION update_deck_card_count();

-- ── User ↔ Deck enrollment ────────────────────────────────────
CREATE TABLE deck_enrollments (
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    deck_id     UUID NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, deck_id)
);

-- ── SRS: per-user card state (FSRS fields) ───────────────────
CREATE TABLE user_cards (
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_id         UUID NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    -- FSRS 4.5 state
    stability       FLOAT NOT NULL DEFAULT 0,
    difficulty      FLOAT NOT NULL DEFAULT 0,
    due_date        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_review     TIMESTAMPTZ,
    reps            INT NOT NULL DEFAULT 0,
    lapses          INT NOT NULL DEFAULT 0,
    state           TEXT NOT NULL DEFAULT 'new'
                        CHECK (state IN ('new','learning','review','relearning')),
    PRIMARY KEY (user_id, card_id)
);

CREATE INDEX user_cards_due_idx ON user_cards(user_id, due_date)
    WHERE state != 'new';

-- ── Review log ────────────────────────────────────────────────
CREATE TYPE review_rating AS ENUM ('again','hard','good','easy');

CREATE TABLE review_logs (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_id         UUID NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    rating          review_rating NOT NULL,
    -- snapshot of FSRS state before this review
    stability_before    FLOAT,
    difficulty_before   FLOAT,
    interval_before     INT,
    -- time spent on card in ms
    elapsed_ms      INT,
    reviewed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX review_logs_user_idx ON review_logs(user_id, reviewed_at DESC);

-- ── Payments ──────────────────────────────────────────────────
CREATE TYPE payment_status AS ENUM ('pending','success','failed','refunded');
CREATE TYPE payment_provider AS ENUM ('telegram_stars','yookassa','robokassa');

CREATE TABLE payments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    provider        payment_provider NOT NULL,
    amount          NUMERIC(10,2),
    currency        TEXT DEFAULT 'RUB',
    status          payment_status NOT NULL DEFAULT 'pending',
    provider_ref    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Placement test results ────────────────────────────────────
CREATE TABLE placement_results (
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    cefr_level      TEXT NOT NULL,
    score           INT NOT NULL,
    answers         JSONB NOT NULL DEFAULT '[]',
    taken_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, tenant_id)
);
