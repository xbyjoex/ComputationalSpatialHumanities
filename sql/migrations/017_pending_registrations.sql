-- =============================================================================
-- Migration 017: Pending registrations (Telegram-Freigabe-Flow)
-- =============================================================================
-- Registrierungen legen nicht mehr direkt einen Nutzer an: das Backend
-- speichert eine Anfrage hier und schickt eine Telegram-Nachricht mit
-- Inline-Buttons an den Admin-Chat; der ETL-Bot (etl/src/telegram_bot.py)
-- verarbeitet den Button-Klick und legt bei Freigabe den Nutzer an.
-- Eine Anfrage ist 5 Minuten gültig (expires_at); danach darf keine
-- Freigabe mehr zu einem Nutzer führen.

CREATE TABLE IF NOT EXISTS auth.pending_registrations (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email         TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    full_name     TEXT,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    requested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ NOT NULL,
    decided_at    TIMESTAMPTZ
);

-- Höchstens eine offene Anfrage pro E-Mail (abgelaufene werden vor dem
-- Insert im Backend auf 'expired' gesetzt, damit der Index nicht blockiert).
CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_reg_email_pending
    ON auth.pending_registrations (email)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_pending_reg_status
    ON auth.pending_registrations (status, expires_at);
