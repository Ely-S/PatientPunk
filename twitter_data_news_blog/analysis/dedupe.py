"""Copy-paste clustering, commercial-intent matching and account age, for the bots section.

Posts are reduced to a bare key (no links, @mentions, case or punctuation). Keys that share
enough word 4-shingles (Jaccard >= threshold, found by MinHash LSH) join one cluster, so a
template with a swapped name or an added hashtag still counts as one text.
"""
import html, re, zlib
import numpy as np
import pandas as pd

URL = re.compile(r"https?://\S+")
# Pruned by reading every term's matches: "dm me", "telegram", "iherb", "affiliate", "promo code",
# "buy online" and a bare "coupon" matched mostly patients, researchers and jokes.
COMMERCIAL_TERMS = [
    r"referred me to (?:chloe|alexa)", r"i was referred to alexa", r"she also (?:vends|gives out medication)",
    r"helped me (?:out )?with (?:ivermectin|hcq)",
    r"whatsapp", r"contact (?:her|him|them) (?:on|via)", r"use (?:my )?code", r"discount code", r"\b\d+ ?% off\b",
    r"\border (?:now|here|today|yours)\b", r"shop now", r"free shipping", r"ships (?:worldwide|to)", r"doorstep",
    r"#ad\b", r"genixmeds", r"onuniversal", r"ivermectinotc", r"ziverdo", r"best place to buy", r"hurry\s+up\s*:"]
COMMERCIAL = re.compile("|".join(f"(?:{p})" for p in COMMERCIAL_TERMS))
P31 = (1 << 31) - 1


def key(t):
    t = URL.sub(" ", html.unescape(t or "").lower())
    t = re.sub(r"@\w+|u/\w+", " ", t)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def _shingles(k, n=4, cap=200):
    w = k.split()[:cap]
    return {zlib.crc32(" ".join(w[i:i + n]).encode()) for i in range(len(w) - n + 1)}


def clusters(keys, threshold=0.6, perms=64, bands=16, seed=1):
    """Cluster id for each key. threshold=None gives exact-key clusters only. Keys under
    10 characters never cluster."""
    keys = pd.Series(keys).reset_index(drop=True)
    uniq = keys[keys.str.len() >= 10].unique()
    parent = {k: k for k in uniq}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x

    if threshold is not None:
        rng = np.random.default_rng(seed)
        a = rng.integers(1, P31, perms, dtype=np.int64); b = rng.integers(0, P31, perms, dtype=np.int64)
        sh = {k: _shingles(k) for k in uniq}
        rows = perms // bands
        buckets = {}
        for k, s in sh.items():
            if not s:
                continue
            h = np.fromiter(s, np.int64)
            sig = ((np.outer(h, a) + b) % P31).min(axis=0)
            for i in range(bands):
                buckets.setdefault((i, sig[i * rows:(i + 1) * rows].tobytes()), []).append(k)
        for members in buckets.values():
            anchor = members[0]; sa = sh[anchor]
            for m in members[1:]:
                sm = sh[m]
                if len(sa & sm) / len(sa | sm) >= threshold:
                    parent[find(m)] = find(anchor)
    return keys.map(lambda k: find(k) if k in parent else None)


def roles(P, threshold=0.6, few=1 / 3, min_copies=3):
    """Label each post. P needs columns pid, uid, date, raw (original text) and key.
    Precedence: vendor > flood > coordinated > headline relay > other repeat > organic."""
    P = P.copy()
    P["cid"] = clusters(P.key, threshold).values
    g = P.dropna(subset=["cid"]).groupby("cid")
    size, accts = g.pid.size(), g.uid.nunique()
    link = g.raw.apply(lambda s: s.str.contains(URL).mean())
    P["c_n"] = P.cid.map(size); P["c_a"] = P.cid.map(accts); P["c_link"] = P.cid.map(link)
    rep = P.c_n >= min_copies
    per_acct = P.groupby(["cid", "uid"]).pid.transform("size")
    P["role"] = "organic"
    P.loc[rep, "role"] = "other repeat"
    P.loc[rep & (P.c_a >= 3) & (P.c_a / P.c_n > few) & (P.c_link >= .5), "role"] = "headline relay"
    P.loc[rep & (P.c_a >= 2) & (P.c_a / P.c_n <= few), "role"] = "coordinated"
    P.loc[P.cid.notna() & (per_acct >= min_copies), "role"] = "flood"
    P.loc[P.raw.str.lower().str.contains(COMMERCIAL), "role"] = "vendor"
    P["bot"] = P.role.isin(["vendor", "flood", "coordinated"])
    P = P.sort_values(["date", "pid"])
    P["later_relay"] = (P.role == "headline relay") & P.duplicated("cid")
    return P


def account_created(author_id):
    """Creation date from a Snowflake user id (accounts made since late 2013); None for older ids."""
    i = int(author_id)
    return pd.Timestamp((i >> 22) + 1288834974657, unit="ms").normalize() if i > 10 ** 15 else None
