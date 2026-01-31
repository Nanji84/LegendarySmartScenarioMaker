import streamlit as st
import json
import random
import re
import os
import traceback

SETUP_RULES = {
    1: {"villains": 1, "henchmen": 1, "bystanders": 1},
    2: {"villains": 2, "henchmen": 1, "bystanders": 2},
    3: {"villains": 3, "henchmen": 1, "bystanders": 8},
    4: {"villains": 3, "henchmen": 2, "bystanders": 8},
    5: {"villains": 4, "henchmen": 2, "bystanders": 12}
}


class LegendaryRandomizer:
    def __init__(self, user_sets, player_count):
        self.user_sets = [s.lower().strip() for s in user_sets]
        self.player_count = player_count
        self.data = {}
        self.setup = {}
        self.synergy_tags = []
        self.scheme_mods = {
            "twists": 8,
            "twist_note": "",
            "master_strikes": 5,
            "bystanders_override": None,
            "bystanders_add": 0,
            "extra_villains": 0,
            "extra_henchmen": 0,
            "required_villains": [],
            "required_henchmen": [],
            "hero_deck_count": 5,
            "villain_deck_heroes": 0,
            "required_villain_deck_heroes": [],
            "heroes_from_hero_deck": 0, # <--- NEW FIELD
            "team_versus_counts": None,
            "custom_deck": None,    # <--- NEW FIELD
            "banned_heroes": [],     # <--- NEW FIELD
            "required_hero_deck_includes": [],
            "bystanders_in_hero_deck": 0,
            "tyrant_masterminds_count": 0,
            "sidekicks_in_villain_deck": 0,
            "ambitions_in_villain_deck": 0,
            "officers_in_villain_deck": 0,
            "player_picked_heroes": 0,
            "required_teams": [],
            "henchmen_in_hero_deck_count": 0, # <--- NEW FIELD
            "henchmen_in_hero_deck_obj": None, # <--- NEW FIELD
            "banned_villains": [],
            "banned_henchmen": [],
            "tactics_in_villain_deck": 0,
            "quantum_ambush_scheme": False,
            "henchman_alias": None,
            "wedding_heroes": [],
            "banned_teams_from_open_selection": [],
            "drained_mastermind_required": False,
            "extra_hero_card_count": None
        }
        print(f"2. Randomizer ready for {player_count} players using sets: {self.user_sets}")
    
    def load_data(self):
        print("3. Loading Data Files...")
        files = {
            "heroes": "enriched_heroes.json",
            "masterminds": "enriched_masterminds.json",
            "villains": "enriched_villains.json",
            "henchmen": "enriched_henchmen.json",
            "schemes": "enriched_schemes.json"
        }
        
        loaded_count = 0
        for key, filename in files.items():
            if not os.path.exists(filename):
                print(f"   [!] CRITICAL: Missing {filename}. Cannot proceed.")
                return False
            
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                
                self.data[key] = [
                    item for item in raw_data 
                    if self._is_in_set(item.get('set', ''))
                ]
                
                count = len(self.data[key])
                print(f"   - Loaded {count} {key}")
                if count > 0: loaded_count += 1

            except Exception as e:
                print(f"   [!] Error loading {filename}: {e}")
                return False

        if loaded_count == 0:
            print("   [!] ERROR: No data loaded! Check your set names.")
            return False
        return True

    def _is_in_set(self, item_set_str):
        if not item_set_str: return False
        item_sets = [s.strip().lower() for s in item_set_str.split('/')]
        return any(s in self.user_sets for s in item_sets)

    def _get_hero_team(self, hero_obj):
        if 'cards' in hero_obj and len(hero_obj['cards']) > 0:
            team = hero_obj['cards'][0].get('team')
            # Check if team is None or empty string, fallback to 'Unknown'
            return team if team else 'Unknown'
        return 'Unknown'

    def _get_tags(self, obj):
        if 'tags' not in obj: return []
        flat_tags = []
        for category, tags in obj['tags'].items():
            flat_tags.extend(tags)
        return flat_tags

    def _get_hero_tags(self, hero):
        all_tags = set()
        team = self._get_hero_team(hero)
        if team and team != 'Unknown':
             clean_team = team.replace('-', ' ').title().replace(' ', '')
             all_tags.add(f"Team_{clean_team}")
        for card in hero['cards']:
            if 'tags' in card:
                for cat, tags in card['tags'].items():
                    for t in tags: all_tags.add(t)
        return list(all_tags)

    def _find_group_by_name(self, name_fragment, group_type):
        target_list = self.data['henchmen'] if group_type == 'henchmen' else self.data['villains']
        # Exact match
        for g in target_list:
            g_name = g.get('name') or g.get('group_name')
            if g_name.lower() == name_fragment.lower(): return g
        # Fuzzy match
        singular = name_fragment.rstrip('s')
        for g in target_list:
            g_name = g.get('name') or g.get('group_name')
            if singular.lower() in g_name.lower(): return g
        return None

    def parse_scheme_rules(self, scheme):
        """Intelligent parsing for Setup mechanics."""
        text = " ".join(scheme.get('description', []))
        
        # --- 0. VILLAIN COUNT OVERRIDES (NEW) ---
        # Matches: "1-2 players: Use 3 Villain Groups"
        # Must run BEFORE Twist Math so we know the total Villain count for "Per Reality" logic
        v_override_match = re.search(r'(?:For\s+)?(\d+)(?:-(\d+))?\s+players:?.*?Use (\d+) Villain Groups', text, re.IGNORECASE)
        if v_override_match:
            low = int(v_override_match.group(1))
            high = int(v_override_match.group(2)) if v_override_match.group(2) else low
            target = int(v_override_match.group(3))
            
            if low <= self.player_count <= high:
                # Calculate how many extras we need to reach the target
                # We use SETUP_RULES directly since self.setup['villains'] isn't populated yet
                base_v = SETUP_RULES.get(self.player_count, {}).get('villains', 2)
                diff = target - base_v
                if diff > 0:
                    self.scheme_mods['extra_villains'] = diff
        
# --- # --- 1. TWIST MATH (FIXED PRIORITIES) ---
        explicit_twist_found = False
        
        # A. PER REALITY CHECK (Highest Priority - Nexus Scheme)
        # Matches: "Add 2 Twists to each Reality"
        reality_twist = re.search(r'Add (\d+) Twists to each Reality', text, re.IGNORECASE)
        if reality_twist:
            per_reality = int(reality_twist.group(1))
            
            # Total Villains = Base + Extra (calculated in Section 0)
            base_v = SETUP_RULES.get(self.player_count, {}).get('villains', 2)
            total_v = base_v + self.scheme_mods['extra_villains']
            
            self.scheme_mods['twists'] = per_reality * total_v
            self.scheme_mods['twist_note'] = f"({per_reality} per Reality x {total_v} Realities)"
            explicit_twist_found = True

        # B. SPECIFIC OVERRIDES (Ranges or Lists)
        # Matches patterns like: "2 players: 9 Twists", "1 or 4 players: 10 Twists"
        # Only run if we didn't find a higher priority rule (like Per Reality)
        if not explicit_twist_found:
            specific_matches = re.finditer(r'(?:For\s+)?([0-9\s\-,or]+?)\s+players:?.*?(?:use\s*)?(\d+)\s+Twists', text, re.IGNORECASE)
            
            for m in specific_matches:
                condition_str = m.group(1).strip()
                val = int(m.group(2))
                is_match = False
                
                # Range Check (e.g. "2-3")
                if '-' in condition_str:
                    parts = condition_str.split('-')
                    if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                        low, high = int(parts[0]), int(parts[1])
                        if low <= self.player_count <= high:
                            is_match = True
                
                # List Check (e.g. "1 or 4")
                else:
                    nums = [int(n) for n in re.findall(r'\d+', condition_str)]
                    if self.player_count in nums:
                        is_match = True
                
                if is_match:
                    self.scheme_mods['twists'] = val
                    self.scheme_mods['twist_note'] = f"(For {condition_str} players)"
                    explicit_twist_found = True
                    break

        # 2. STANDARD FORMULAS (Fallback)
        if not explicit_twist_found:
            # ... (Paste your existing standard formula logic here: A, B, C, D, E) ...
            # DEFINITIONS
            # A. Base +/- Mod (Prioritized): "11 Twists, minus 1 Twist per player"
            base_mod_match = re.search(r'(\d+)\s+Twists.*?(minus|plus)\s+(\d+)(?:\s+Twists?)?\s+per\s+player', text, re.IGNORECASE)
            
            # B. Players + X: "Twists equal to the number of players plus 6"
            players_plus_match = re.search(r'Twists equal to the number of players plus (\d+)', text, re.IGNORECASE)
            
            # C. Mixed: "1 Twist, plus 2 per player"
            mixed_match = re.search(r'(\d+)\s+Twists?,?\s+plus\s+(\d+)\s+Twists?\s+per\s+player', text, re.IGNORECASE)
            
            # D. Pure Multiplier: "2 Twists per player"
            per_player_each = re.search(r'(\d+)\s+Twists? (?:into each|per) player', text, re.IGNORECASE)
            
            # E. Simple Base: "8 Twists"
            base_twist = re.search(r'(\d+)\s+Twists', text, re.IGNORECASE)

            # LOGIC CHAIN
            if base_mod_match:
                base = int(base_mod_match.group(1))
                op = base_mod_match.group(2).lower()
                mod = int(base_mod_match.group(3))
                
                if op == 'minus':
                    self.scheme_mods['twists'] = base - (mod * self.player_count)
                    self.scheme_mods['twist_note'] = f"({base} - {mod} per player)"
                else:
                    self.scheme_mods['twists'] = base + (mod * self.player_count)
                    self.scheme_mods['twist_note'] = f"({base} + {mod} per player)"

            elif players_plus_match:
                add = int(players_plus_match.group(1))
                self.scheme_mods['twists'] = self.player_count + add
                self.scheme_mods['twist_note'] = f"({self.player_count} players + {add})"
                
            elif mixed_match:
                base = int(mixed_match.group(1))
                per_player = int(mixed_match.group(2))
                self.scheme_mods['twists'] = base + (per_player * self.player_count)
                self.scheme_mods['twist_note'] = f"({base} + {per_player} per player)"
                
            elif per_player_each:
                count = int(per_player_each.group(1))
                self.scheme_mods['twists'] = count * self.player_count
                self.scheme_mods['twist_note'] = f"({count} per player)"
                
            elif base_twist:
                val = int(base_twist.group(1))
                self.scheme_mods['twists'] = val
                
                # Check for separate sentence modifiers (rare fallback)
                plus_match = re.search(r'plus (\d+)(?: twist| twists)? per player', text, re.IGNORECASE)
                minus_match = re.search(r'minus (\d+)(?: twist| twists)? per player', text, re.IGNORECASE)
                
                if plus_match:
                    add = int(plus_match.group(1))
                    self.scheme_mods['twists'] += (add * self.player_count)
                    self.scheme_mods['twist_note'] = f"({val} + {add} per player)"
                elif "plus 1 per player" in text.lower():
                     self.scheme_mods['twists'] += self.player_count
                     self.scheme_mods['twist_note'] = f"({val} + 1 per player)"
                     
                if minus_match:
                    sub = int(minus_match.group(1))
                    self.scheme_mods['twists'] -= (sub * self.player_count)
                    self.scheme_mods['twist_note'] = f"({val} - {sub} per player)"
                elif "minus 1 twist per player" in text.lower():
                     self.scheme_mods['twists'] -= self.player_count
                     self.scheme_mods['twist_note'] = f"({val} - 1 per player)"

        # --- 0. VERSUS TEAMS ---
        versus_match = re.search(r'(\d+) Heroes of one Team and (\d+) Heroes of another', text, re.IGNORECASE)
        if versus_match:
            count_a = int(versus_match.group(1))
            count_b = int(versus_match.group(2))
            self.scheme_mods['hero_deck_count'] = count_a + count_b
            self.scheme_mods['team_versus_counts'] = (count_a, count_b)

        # --- 2. MASTER STRIKES ---
        ms_match = re.search(r'(\d+)\s+Master Strikes', text, re.IGNORECASE)
        if ms_match:
            self.scheme_mods['master_strikes'] = int(ms_match.group(1))

        # --- 3. BYSTANDERS ---
        if re.search(r'no Bystanders', text, re.IGNORECASE):
            self.scheme_mods['bystanders_override'] = 0
        else:
            total_bys = re.search(r'(\d+)\s+total\s+Bystanders', text, re.IGNORECASE)
            if total_bys:
                self.scheme_mods['bystanders_override'] = int(total_bys.group(1))
            
            add_bys = re.search(r'Add\s+(\d+)\s+(?:extra\s+)?Bystanders', text, re.IGNORECASE)
            if add_bys:
                self.scheme_mods['bystanders_add'] = int(add_bys.group(1))

        # --- 4. HERO DECK SIZE (FIXED REGEX) ---
        # Split on '.', '(', ')', or newlines to separate rules
        sentences = re.split(r'[.()\n]', text)
        explicit_found = False
        
        for s in sentences:
            s = s.strip()
            if not s: continue

            # 1. PLAYER CONSTRAINT CHECK
            # Checks for "X-Y Players" or "X Players" at start of sentence
            # Regex now handles "For X-Y Players" or just "X-Y Players:" and various dash types
            p_match = re.search(r'^(?:For\s+)?(\d+)(?:[-\u2013\u2014](\d+))?\s+players?', s, re.IGNORECASE)
            if p_match:
                low = int(p_match.group(1))
                high = int(p_match.group(2)) if p_match.group(2) else low
                if not (low <= self.player_count <= high):
                    continue # Constraint found but doesn't apply to this player count

            # 2. CHECK FOR ADDITIVE RULES ("Add another Hero", "Add 1 extra Hero")
            # FIX: Changed 'Heroes?' (matches Heroe/Heroes) to 'Hero(?:es)?' (matches Hero/Heroes)
            add_match = re.search(r'Add\s+(?:an|another|(\d+)|(one|two|three))\s+(?:extra\s+)?Hero(?:es)?(?!\s+(?:to|into|in)\s+(?:the\s+)?Villain Deck)', s, re.IGNORECASE)
            
            # 3. CHECK FOR BASE COUNT RULES ("Use 5 Heroes", "Hero Deck is 4 Heroes")
            base_match = re.search(r'(\d+)\s+Heroes', s, re.IGNORECASE)
            
            if add_match:
                to_add = 1
                if add_match.group(1): # Digit (e.g. "2")
                    to_add = int(add_match.group(1))
                elif add_match.group(2): # Word (e.g. "two")
                    word_map = {"one": 1, "two": 2, "three": 3}
                    to_add = word_map.get(add_match.group(2).lower(), 1)
                
                # Ensure base is set to 5 if currently 0/default before adding
                if self.scheme_mods['hero_deck_count'] == 0:
                     self.scheme_mods['hero_deck_count'] = 5
                
                self.scheme_mods['hero_deck_count'] += to_add

            elif base_match:
                val = int(base_match.group(1))
                is_explicit = "hero deck" in s.lower()

                if explicit_found and not is_explicit: continue
                if val >= 10 and not is_explicit: continue 

                self.scheme_mods['hero_deck_count'] = val
                if is_explicit: explicit_found = True

        # --- 5. VILLAIN DECK HEROES (FIXED v2) ---
        # Pattern A: "includes 14 extra Jean Grey cards"
        match_a = re.search(r'includes \d+ extra (.*?) cards', text, re.IGNORECASE)
        
        # Pattern B: "Add 14 Jean Grey Hero cards to the Villain Deck"
        match_b = re.search(r'Add \d+ (.*?) Hero cards to the Villain Deck', text, re.IGNORECASE)

        # Pattern C: "cards for any Blade Hero"
        match_c = re.search(r'cards for (?:any|an) (.*?) Hero', text, re.IGNORECASE)

        # Pattern E: "Add 8 random cards from an extra Hero" (NEW)
        # Matches: "Add 8 random cards from an extra Hero to the Villain Deck"
        match_e = re.search(r'Add (\d+) (?:random )?cards from an extra Hero', text, re.IGNORECASE)

        if match_a:
            self.scheme_mods['villain_deck_heroes'] += 1
            name = match_a.group(1).strip()
            if "extra" not in name.lower(): self.scheme_mods['required_villain_deck_heroes'].append(name)
            
        elif match_b:
            self.scheme_mods['villain_deck_heroes'] += 1
            self.scheme_mods['required_villain_deck_heroes'].append(match_b.group(1).strip())
            
        elif match_c:
             self.scheme_mods['villain_deck_heroes'] += 1
             name = match_c.group(1).strip()
             if "extra" not in name.lower(): self.scheme_mods['required_villain_deck_heroes'].append(name)

        elif match_e:
             self.scheme_mods['villain_deck_heroes'] += 1
             # Capture the specific quantity (e.g. 8)
             self.scheme_mods['extra_hero_card_count'] = int(match_e.group(1))

        # Pattern D: Generic Fallback (e.g. "Add an extra Hero to the Villain Deck")
        # Updated to accept "to the Villain Deck" (not just "into")
        elif re.search(r'(?:to|into|in) the Villain Deck.*?extra Hero', text, re.IGNORECASE) or \
             re.search(r'Villain Deck includes.*?extra Hero', text, re.IGNORECASE):
            self.scheme_mods['villain_deck_heroes'] += 1

        # --- 6. EXTRA GROUPS (FIXED) ---
        # 1. Check for "Solo" conditional first (Specific)
        if re.search(r'If playing solo.*?add.*?Villain Group', text, re.IGNORECASE):
            if self.player_count == 1:
                self.scheme_mods['extra_villains'] += 1
        
        # 2. Check for standard unconditional addition (Generic)
        # Matches: "Add an extra...", "Add 2 extra...", "Add two extra..."
        elif re.search(r'Add (?:an|(\d+)|(one|two|three|four)) extra Villain Groups?', text, re.IGNORECASE):
            m = re.search(r'Add (?:an|(\d+)|(one|two|three|four)) extra Villain Groups?', text, re.IGNORECASE)
            count = 1
            if m.group(1): # Digit found (e.g. "2")
                count = int(m.group(1))
            elif m.group(2): # Word found (e.g. "two")
                word_map = {"one": 1, "two": 2, "three": 3, "four": 4}
                count = word_map.get(m.group(2).lower(), 1)
            
            self.scheme_mods['extra_villains'] += count
            
        # Henchmen Logic (Updated for quantities)
        hench_match = re.search(r'Add (?:an|another|(\d+)|(one|two|three|four)) (?:extra )?Henchm[ae]n', text, re.IGNORECASE)
        if hench_match:
            count = 1
            if hench_match.group(1): # Digit found
                count = int(hench_match.group(1))
            elif hench_match.group(2): # Number word found
                word_map = {"one": 1, "two": 2, "three": 3, "four": 4}
                count = word_map.get(hench_match.group(2).lower(), 1)
            # If "an" or "another" matched (and groups 1/2 are None), count defaults to 1
            self.scheme_mods['extra_henchmen'] += count
            
        # --- 6b. HENCHMAN GROUP ALIAS (NEW) ---
        # Matches: "Add an extra Henchman Group ... as 'Xerogen Experiments'"
        # Note: The count (+1) is handled by the generic regex above. We just capture the name here.
        alias_match = re.search(r'Add an extra Henchman Group.*?as [\"“\'](.*?)[\"“\”\']', text, re.IGNORECASE)
        if alias_match:
            self.scheme_mods['henchman_alias'] = alias_match.group(1).strip()

        # --- 7. NAMED REQUIREMENTS (FIXED) ---
        # Matches: "Include 10 Sentinels as extra Henchmen" OR "as one of the Backup Adversary groups"
        # Updated Regex: Accepts "Backup Adversary" (and plural) as synonym for Henchmen
        matches = re.findall(r'(Include|Add) (?:\d+ )?(.*?) as (?:an? )?(extra )?(?:one of the )?(Henchm[ae]n|Villain|Backup Adversar(?:y|ies))', text, re.IGNORECASE)
        
        for action, name, is_extra, gtype in matches:
            clean_name = name.strip()
            
            # Decide if we need to add a slot
            # We add a slot if it explicitly says "extra" OR "Add" (usually implies extra in this context)
            should_add_slot = bool(is_extra) or action.lower() == "add"
            
            # Check for Henchmen OR Backup Adversaries
            is_henchman = "hench" in gtype.lower() or "backup" in gtype.lower()
            
            if is_henchman:
                self.scheme_mods['required_henchmen'].append(clean_name)
                if should_add_slot:
                    # Only increase if we haven't covered it with the generic counters
                    if self.scheme_mods['extra_henchmen'] < len(self.scheme_mods['required_henchmen']):
                         self.scheme_mods['extra_henchmen'] = len(self.scheme_mods['required_henchmen'])
            else:
                self.scheme_mods['required_villains'].append(clean_name)
                if should_add_slot:
                    if self.scheme_mods['extra_villains'] < len(self.scheme_mods['required_villains']):
                        self.scheme_mods['extra_villains'] = len(self.scheme_mods['required_villains'])
       # --- 7b. IMPLICIT INCLUSION (ROBUST V3) ---
        # Matches: "Always include Party Thor Hero and Intergalactic Party Animals Villain Group."
        implicit_match = re.search(r'Always include (?:the )?(.*?)(?:\.|$)', text, re.IGNORECASE)
        if implicit_match:
            content = implicit_match.group(1)
            
            # 1. Robust Split: Handles "," "and" ", and" with any spacing
            parts = re.split(r',\s*and\s+|\s+and\s+|,\s*', content)
            
            for part in parts:
                name_frag = part.strip()
                if not name_frag: continue
                
                # 2. Clean up generic words with WORD BOUNDARIES (\b)
                # Removes "Hero", "Villain Group" etc. but only as whole words
                clean_frag = re.sub(r'\b(?:Villain Groups?|Henchm[ae]n Groups?|Villains?|Henchm[ae]n|Heroes?|Hero)\b', '', name_frag, flags=re.IGNORECASE).strip()
                
                # Remove leading "the" if it remains (e.g. "and the Skrulls")
                clean_frag = re.sub(r'^the\s+', '', clean_frag, flags=re.IGNORECASE).strip()
                
                if not clean_frag: clean_frag = name_frag 
                
                # Helper: Word-based Fuzzy Match (Fixes "Part" vs "Party" typos)
                def strict_or_word_match(target_name, search_query):
                    if not target_name: return False
                    t_lower = target_name.lower()
                    q_lower = search_query.lower()
                    # A. Substring Match (Standard)
                    if q_lower in t_lower: return True
                    # B. Word Subset Match (Typo Fallback)
                    # Checks if all significant words in query exist in target (e.g. "Intergalactic" + "Part" in "Intergalactic Party")
                    q_words = [w for w in re.findall(r'\w+', q_lower) if len(w) > 2]
                    if not q_words: return False
                    matches = 0
                    for qw in q_words:
                        if qw in t_lower: matches += 1
                    # If 75% of query words are present, it's a match
                    return matches >= len(q_words) * 0.75

                # 3. Try Finding Group/Hero with Fallback Logic
                
                # A. Try Henchmen
                found_h = None
                for h in self.data['henchmen']:
                     if strict_or_word_match(h.get('name') or h.get('group_name'), clean_frag):
                         found_h = h; break
                if found_h:
                    self.scheme_mods['required_henchmen'].append(found_h['name'])
                    continue 

                # B. Try Villains
                found_v = None
                for v in self.data['villains']:
                     if strict_or_word_match(v.get('group_name') or v.get('name'), clean_frag):
                         found_v = v; break
                if found_v:
                    self.scheme_mods['required_villains'].append(found_v['group_name'])
                    continue

                # C. Try Heroes
                # Use standard fuzzy first, then custom word match
                found_hero = self._find_hero_by_name(clean_frag)
                if not found_hero:
                    for h in self.data['heroes']:
                        if strict_or_word_match(h['hero'], clean_frag):
                            found_hero = h; break
                
                if found_hero:
                    self.scheme_mods['required_hero_deck_includes'].append({'name': found_hero['hero'], 'count': 1})
        # --- 8. EXPLICIT GROUP REQUIREMENTS (NEW) ---
        # Matches: "Skrull Villain Group required"
        req_group = re.search(r'([a-zA-Z\s]+) Villain Group required', text, re.IGNORECASE)
        if req_group:
            self.scheme_mods['required_villains'].append(req_group.group(1).strip())
            
        # --- 8b. KEYWORD GROUP REQUIREMENTS (FIXED CLEANUP) ---
        # Matches: "Include exactly one Villain Group with 'Rise of The Living Dead'"
        # Updated Regex: Handles extra spaces and punctuation inside the quotes
        keyword_req_match = re.search(r'Include exactly (one|two|three|\d+) Villain Groups? with [\"“\']\s*(.*?)\s*[\"“\”\']', text, re.IGNORECASE)
        if keyword_req_match:
            count_str = keyword_req_match.group(1).lower()
            
            # AGGRESSIVE CLEANUP: 
            # 1. Capture raw string (e.g. " Rise of The Living Dead .")
            # 2. Remove periods completely
            # 3. Strip whitespace from both ends
            raw_keyword = keyword_req_match.group(2)
            keyword = raw_keyword.replace('.', '').strip()
            
            # Parse quantity
            word_map = {"one": 1, "two": 2, "three": 3}
            count = int(count_str) if count_str.isdigit() else word_map.get(count_str, 1)
            
            # Search for candidate groups
            candidates = []
            for group in self.data['villains']:
                has_keyword = False
                for card in group.get('cards', []):
                    # Check text inside abilities
                    for ability in card.get('abilities', []):
                        if keyword.lower() in ability.lower():
                            has_keyword = True
                            break
                    if has_keyword: break
                
                if has_keyword:
                    candidates.append(group['group_name'])
            
            # Select and apply
            if candidates:
                # Filter out ones already required to avoid duplicates
                available = [c for c in candidates if c not in self.scheme_mods['required_villains']]
                if not available: available = candidates 
                
                if len(available) >= count:
                    chosen = random.sample(available, count)
                    self.scheme_mods['required_villains'].extend(chosen)
                else:
                    print(f"   [!] Warning: Not enough groups with '{keyword}'. Found: {available}")
                    self.scheme_mods['required_villains'].extend(available)
            else:
                print(f"   [!] Warning: No Villain Group found with keyword '{keyword}'.")

        # --- 9. HEROES MOVED FROM HERO DECK (NEW) ---
        # Matches: "Shuffle 12 random Heroes from the Hero Deck into the Villain Deck"
        moved_heroes = re.search(r'Shuffle (\d+) random Heroes from the Hero Deck into the Villain Deck', text, re.IGNORECASE)
        if moved_heroes:
            self.scheme_mods['heroes_from_hero_deck'] = int(moved_heroes.group(1))
            
        # --- 10. EITHER/OR SELECTION (FIXED) ---
        # Updated to handle weird quoting (e.g. using open quotes as closing quotes)
        either_match = re.search(r'Include either (?:the )?[\"“\'](.+?)[\"“\”\'] or [\"“\'](.+?)[\"“\”\'] Villain Group', text, re.IGNORECASE)
        if either_match:
            choice = random.choice([either_match.group(1), either_match.group(2)])
            self.scheme_mods['required_villains'].append(choice.strip())
            
        # --- 11. CUSTOM DECKS (FIXED) ---
        # Updated regex to handle "weird" quotes (using open quotes as closers)
        
        # A. Infected Deck
        infected_match = re.search(r'Shuffle together (\d+) Bystanders and (\d+) (.*?) Henchmen as an [\"“\'](.*?)[\"“\”\']', text, re.IGNORECASE)
        if infected_match:
            bys_count = infected_match.group(1)
            hench_count = infected_match.group(2)
            hench_name_frag = infected_match.group(3).strip()
            deck_title = infected_match.group(4).strip().rstrip('.') # Strip trailing period if captured
            
            hench_obj = self._find_group_by_name(hench_name_frag, 'henchmen')
            if hench_obj:
                full_hench_name = f"{hench_obj['name']} ({hench_obj['set']})"
                self.scheme_mods['required_henchmen'].append("RESERVED_FOR_CUSTOM") 
            else:
                full_hench_name = f"{hench_name_frag} (Unknown)"

            self.scheme_mods['custom_deck'] = {
                "name": deck_title,
                "lines": [f"{bys_count} Bystanders", f"{hench_count} {full_hench_name}"]
            }

        # B. Hulk Deck / Mutation Pile
        # Regex broadened to handle "Shuffle them into" AND "Put them in a face-up..."
        hulk_deck_match = re.search(r'Hero with [\"“\'](.*?)[\"“\”\'] in its Hero Name.*?(?:Shuffle|Put) them (?:into|in) (?:a )?(?:face-up )?[\"“\'](.*?)[\"“\”\']', text, re.IGNORECASE)
        if hulk_deck_match:
            keyword = hulk_deck_match.group(1)
            deck_title = hulk_deck_match.group(2).strip().rstrip('.')
            
            # Find a hero matching the keyword
            candidates = [h for h in self.data['heroes'] if keyword.lower() in h['hero'].lower()]
            if candidates:
                chosen = random.choice(candidates)
                self.scheme_mods['banned_heroes'].append(chosen['hero'])
                
                self.scheme_mods['custom_deck'] = {
                    "name": deck_title,
                    "lines": [f"14 cards of {chosen['hero']} ({chosen['set']})"]
                }
         # C. Dark Loyalty / Standard Additional Hero Deck (NEW)
        # Matches: "Randomly pick 5 cards... from an additional Hero... form a “Dark Loyalty“ deck"
        loyalty_match = re.search(r'Randomly pick (\d+) cards.*?from an additional Hero.*?form a [\"“\'](.*?)[\"“\”\'] deck', text, re.IGNORECASE)
        if loyalty_match:
            count = int(loyalty_match.group(1))
            deck_title = loyalty_match.group(2).strip()
            
            # Pick a random additional hero
            candidates = [h for h in self.data['heroes'] if h['hero'] not in self.scheme_mods['banned_heroes']]
            if candidates:
                chosen = random.choice(candidates)
                self.scheme_mods['banned_heroes'].append(chosen['hero'])
                
                # Check if there is a cost restriction in the text to include in the note
                note = ""
                if "cost 5 or less" in text.lower():
                    note = " (cost 5 or less)"
                
                self.scheme_mods['custom_deck'] = {
                    "name": deck_title,
                    "lines": [f"{count} cards{note} of {chosen['hero']} ({chosen['set']})"]
                }
        # --- D. SHRINK TECH (NEW) ---
        # Matches: "Set aside all 14 cards of a random extra Hero that has any Size-Changing cards as “Shrink Tech.“"
        shrink_match = re.search(r'Set aside all 14 cards of a random extra Hero that has any Size-Changing cards as [\"“\'](.*?)[\"“\”\']', text, re.IGNORECASE)
        if shrink_match:
            deck_title = shrink_match.group(1).strip().rstrip('.')
            
            # Filter for Heroes with "Size-Changing" in their abilities
            candidates = []
            for h in self.data['heroes']:
                if h['hero'] in self.scheme_mods['banned_heroes']: continue
                
                has_mechanism = False
                for card in h.get('cards', []):
                    # Check text inside abilities
                    for ability in card.get('abilities', []):
                        if "Size-Changing" in ability:
                            has_mechanism = True
                            break
                    if has_mechanism: break
                
                if has_mechanism: candidates.append(h)
            
            if candidates:
                chosen = random.choice(candidates)
                self.scheme_mods['banned_heroes'].append(chosen['hero'])
                self.scheme_mods['custom_deck'] = {
                    "name": deck_title,
                    "lines": [f"14 cards of {chosen['hero']} ({chosen['set']})"]
                }
            else:
                print("   [!] Warning: No Heroes with 'Size-Changing' abilities found for Shrink Tech.")
                
        # --- E WEDDING HEROES (NEW) ---
        # Matches: "Set aside two extra Heroes to get married"
        if re.search(r'Set aside (?:two|2) extra Heroes to get married', text, re.IGNORECASE):
            # Pick 2 random heroes not already banned
            candidates = [h for h in self.data['heroes'] if h['hero'] not in self.scheme_mods['banned_heroes']]
            
            if len(candidates) >= 2:
                wed_heroes = random.sample(candidates, 2)
                self.scheme_mods['wedding_heroes'] = wed_heroes
                
                # Ban them so they don't appear in the main Hero Deck
                for h in wed_heroes:
                    self.scheme_mods['banned_heroes'].append(h['hero'])
            else:
                print("   [!] Warning: Not enough heroes available for Wedding setup.")
                
        # --- F. PAST HERO DECK (FIXED) ---
        # Matches: "plus 4 other Heroes to make a ”Past Hero Deck”"
        # Regex updated to accept ” as an opening quote
        past_deck_match = re.search(r'plus (\d+) other Heroes to make a\s*[\"“\”\'](.*?)[\"“\”\']', text, re.IGNORECASE)
        if past_deck_match:
            count = int(past_deck_match.group(1))
            deck_name = past_deck_match.group(2).strip().rstrip('.') # Strip trailing period if inside quotes
            
            # Pick random heroes not already banned
            candidates = [h for h in self.data['heroes'] if h['hero'] not in self.scheme_mods['banned_heroes']]
            
            if len(candidates) >= count:
                chosen = random.sample(candidates, count)
                
                # Ban them so they don't appear in the main Hero Deck
                for h in chosen:
                    self.scheme_mods['banned_heroes'].append(h['hero'])
                
                # Register as a Custom Deck for display
                self.scheme_mods['custom_deck'] = {
                    "name": deck_name,
                    "lines": [f"{h['hero']} ({h['set']})" for h in chosen]
                }
            else:
                print(f"   [!] Warning: Not enough heroes available for {deck_name}.")
                
        # --- G MONSTER PIT / CUSTOM VILLAIN DECK (NEW) ---
        # Matches: "Shuffle 8 Monsters Unleashed Villains into a face-down 'Monster Pit' deck."
        monster_pit_match = re.search(r'Shuffle (\d+) (.*?) Villains into a .*?[\"“\'](.*?)[\"“\”\'] deck', text, re.IGNORECASE)
        if monster_pit_match:
            count = int(monster_pit_match.group(1))
            v_group_name = monster_pit_match.group(2).strip()
            deck_name = monster_pit_match.group(3).strip()
            
            # Find the villain group
            v_obj = self._find_group_by_name(v_group_name, 'villains')
            
            if v_obj:
                # Ban it from normal selection
                self.scheme_mods['banned_villains'].append(v_obj.get('group_name') or v_obj.get('name'))
                
                # Create Custom Deck entry
                self.scheme_mods['custom_deck'] = {
                    "name": deck_name,
                    "lines": [f"{count} cards from {v_obj.get('group_name') or v_obj.get('name')} ({v_obj['set']})"]
                }
            else:
                print(f"   [!] Warning: Could not find Villain Group '{v_group_name}' for {deck_name}.")
        
        # --- 12. HERO DECK NAME REQUIREMENTS (FIXED) ---
        # Pattern A: Quotes (e.g. "Use exactly two Heroes with 'Hulk' in their Hero Names")
        hero_inc_match = re.search(r'Use exactly (\w+) Heroes with [\"“\'](.*?)[\"“\”\'] in their Hero Names', text, re.IGNORECASE)
        
        # Pattern B: Explicit Single (e.g. "Exactly one Hero must be a Nova Hero")
        # Captures the name (e.g. "Nova") before the word "Hero"
        single_req_match = re.search(r'Exactly one Hero must be a (.*?) Hero(?:[\.\n]|$)', text, re.IGNORECASE)
        use_as_match = re.search(r'Use (.*?) as one of the Heroes', text, re.IGNORECASE)
        
        # Pattern D: Comedic/Informal (e.g. "Use the best Hero in the game: Deadpool!")
        comedic_match = re.search(r'Use the best Hero.*?: (.*?)(?:!|\.|$)', text, re.IGNORECASE)
        
        # Pattern E: "Include exactly X Hero(es) with Y in name" (NEW)
        # Matches: "Include exactly 1 Hero with Wolverine or Logan in its name"
        # Captures: Count (Group 1), Name(s) (Group 2)
        include_exact_match = re.search(r'(?:Include|Use) exactly (\d+) Hero(?:es)? with (.*?) in (?:its|their) (?:Hero )?Name', text, re.IGNORECASE)

        if hero_inc_match:
            word_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
            count_str = hero_inc_match.group(1).lower()
            count = word_map.get(count_str, 0)
            if count == 0 and count_str.isdigit(): count = int(count_str)
            name_req = hero_inc_match.group(2)
            if count > 0: self.scheme_mods['required_hero_deck_includes'].append({'name': name_req, 'count': count})
            
        elif single_req_match:
            name_req = single_req_match.group(1).strip()
            # "Exactly one" implies count is 1
            self.scheme_mods['required_hero_deck_includes'].append({'name': name_req, 'count': 1})
        elif use_as_match:
             name_req = use_as_match.group(1).strip()
             self.scheme_mods['required_hero_deck_includes'].append({'name': name_req, 'count': 1})
        elif comedic_match:
             name_req = comedic_match.group(1).strip()
             self.scheme_mods['required_hero_deck_includes'].append({'name': name_req, 'count': 1})
        elif include_exact_match:
             self.scheme_mods['required_hero_deck_includes'].append({
                 'name': include_exact_match.group(2).strip(), 
                 'count': int(include_exact_match.group(1))
             })
             
        
                
        # --- 13. BYSTANDERS IN HERO DECK (NEW) ---
        # 1. Default Rule: "24 Bystanders in the Hero Deck"
        def_bys = re.search(r'(\d+)\s+Bystanders in the Hero Deck', text, re.IGNORECASE)
        if def_bys:
            self.scheme_mods['bystanders_in_hero_deck'] = int(def_bys.group(1))
            
        # 2. Specific Override: "(1 player: 12 Bystanders...)"
        spec_bys = re.search(r'\((\d+)\s+player:\s+(\d+)\s+Bystanders', text, re.IGNORECASE)
        if spec_bys:
            req_players = int(spec_bys.group(1))
            req_count = int(spec_bys.group(2))
            if self.player_count == req_players:
                self.scheme_mods['bystanders_in_hero_deck'] = req_count
        
        # --- 14. SIDEKICKS IN VILLAIN DECK (NEW) ---
        # Matches: "Add 10 Sidekicks to the Villain Deck"
        sidekick_match = re.search(r'Add (\d+) Sidekicks to the Villain Deck', text, re.IGNORECASE)
        if sidekick_match:
            self.scheme_mods['sidekicks_in_villain_deck'] = int(sidekick_match.group(1))
            
        # --- 15. AMBITION CARDS (NEW) ---
        # Matches: "Add 10 random Ambition cards to the Villain Deck"
        ambition_match = re.search(r'Add (\d+) (?:random )?Ambition cards', text, re.IGNORECASE)
        if ambition_match:
            self.scheme_mods['ambitions_in_villain_deck'] = int(ambition_match.group(1))
            
        # --- 16. OFFICERS IN VILLAIN DECK (NEW) ---
        # Matches: "Add 12 S.H.I.E.L.D. Officers to the Villain Deck"
        # We escape the dots in S.H.I.E.L.D. or just look for "Officers" to be safe
        officer_match = re.search(r'Add (\d+) S\.H\.I\.E\.L\.D\. Officers to the Villain Deck', text, re.IGNORECASE)
        if officer_match:
            self.scheme_mods['officers_in_villain_deck'] = int(officer_match.group(1))
            
        # --- 17. PLAYER PICKED HEROES (NEW) ---
        # Matches: "Each player chooses a Hero to be part of the Hero Deck"
        if re.search(r'Each player chooses a Hero to be part of the Hero Deck', text, re.IGNORECASE):
            self.scheme_mods['player_picked_heroes'] = self.player_count
            
        # --- 18. HERO TEAM REQUIREMENTS (NEW) ---
        # Matches: "Use at least 1 [spider-friends] Hero"
        # Handles brackets [ ] often used for icons in text
        team_req_match = re.search(r'Use at least (\d+) \[?([a-zA-Z0-9\-\s]+)\]? Hero', text, re.IGNORECASE)
        if team_req_match:
            count = int(team_req_match.group(1))
            # Clean up the team name (remove brackets if captured, lowercase)
            team_name = team_req_match.group(2).strip().lower()
            self.scheme_mods['required_teams'].append({'team': team_name, 'count': count})
        # --- 18b. SPECIFIC TEAM COMPOSITION (House of M style) (FIXED) ---
        # Matches: "Hero Deck is 4 [x-men] Heroes and 2 non- [x-men] Heroes"
        split_team_match = re.search(r'Hero Deck is (\d+) \[?([a-zA-Z0-9\-\s]+)\]? Heroes and (\d+)', text, re.IGNORECASE)
        if split_team_match:
            count_team = int(split_team_match.group(1))
            team_name = split_team_match.group(2).strip().lower()
            count_other = int(split_team_match.group(3))
            
            # 1. Update Total Hero Deck Count
            self.scheme_mods['hero_deck_count'] = count_team + count_other
            
            # 2. Add Team Requirement (Forces the 4 X-Men)
            self.scheme_mods['required_teams'].append({'team': team_name, 'count': count_team})
            
            # 3. Ban this team from the remaining slots (Ensures the other 2 are NON-X-Men)
            self.scheme_mods['banned_teams_from_open_selection'].append(team_name)
            
        # --- 19. HENCHMEN IN HERO DECK (NEW) ---
        # Matches: "Add 6 extra Henchmen from a single Henchman Group to the Hero Deck"
        hench_hero_match = re.search(r'Add (\d+) (?:extra )?Henchmen.*?to the Hero Deck', text, re.IGNORECASE)
        if hench_hero_match:
            self.scheme_mods['henchmen_in_hero_deck_count'] = int(hench_hero_match.group(1))
        
        # --- 20. SET ASIDE VILLAIN GROUPS (NEW) ---
        # Matches: "Set aside the 'Quantum Realm' Villain Group"
        set_aside_match = re.search(r'Set aside (?:the )?[\"“\'](.+?)[\"“\”\'] Villain Group', text, re.IGNORECASE)
        if set_aside_match:
            self.scheme_mods['banned_villains'].append(set_aside_match.group(1).strip())
        
        # --- 21. TACTICS IN VILLAIN DECK (NEW) ---
        # Matches: "Shuffle the Mastermind Tactics into the Villain Deck"
        if re.search(r'Shuffle (?:the )?Mastermind Tactics into the Villain Deck', text, re.IGNORECASE):
            self.scheme_mods['tactics_in_villain_deck'] = 4
        # --- 22. QUANTUM AMBUSH SCHEME (NEW) ---
        # Matches: "Shuffle its Ambush Scheme into the Villain Deck"
        if re.search(r'Shuffle its Ambush Scheme into the Villain Deck', text, re.IGNORECASE):
            self.scheme_mods['quantum_ambush_scheme'] = True
            
        # --- 23. STACKED HENCHMEN (NEW) ---
        # Matches: "Stack 2 Cops per player"
        # We check if the captured name is actually a Henchman group to avoid banning non-card items (like "Twists").
        stack_match = re.search(r'Stack \d+ (.*?) per player', text, re.IGNORECASE)
        if stack_match:
            name = stack_match.group(1).strip()
            # Verify it's a Henchman group before banning
            if self._find_group_by_name(name, 'henchmen'):
                self.scheme_mods['banned_henchmen'].append(name)
        
        # --- 24. DRAINED MASTERMIND (NEW) ---
        # Matches: "Set aside a second 'Drained' Mastermind"
        if re.search(r'Set aside a second [\"“\']Drained[\"“\”\'] Mastermind', text, re.IGNORECASE):
            self.scheme_mods['drained_mastermind_required'] = True
            
            # The rule usually says "Add its 'Always Leads' Villains as an extra Villain Group"
            # We must manually increment the count because the generic parser might miss this specific phrasing
            if re.search(r'Add its [\"“\']Always Leads[\"“\”\'] Villains as an extra Villain Group', text, re.IGNORECASE):
                self.scheme_mods['extra_villains'] += 1

    def pick_scheme(self):
        if not self.data.get('schemes'): raise Exception("No Schemes found.")
        scheme = random.choice(self.data['schemes'])
        self.setup['scheme'] = scheme
        self.synergy_tags.extend(self._get_tags(scheme))
        self.setup['special_rules'] = scheme.get('description', [])
        self.parse_scheme_rules(scheme)

    def pick_mastermind(self):
        if not self.data.get('masterminds'): raise Exception("No Masterminds found.")
        
        # 1. Pick Main Mastermind
        mm = random.choice(self.data['masterminds'])
        self.setup['mastermind'] = mm
        self.synergy_tags.extend(self._get_tags(mm))
        
        # Initialize empty list for safety
        self.setup['lurking_masterminds'] = []
        
        # 2. Check for "Lurking" Masterminds
        scheme_text = " ".join(self.setup.get('special_rules', []))
        lurking_match = re.search(r'Put (\w+) additional Masterminds', scheme_text, re.IGNORECASE)
        
        if lurking_match:
            word_map = {"one": 1, "two": 2, "three": 3, "four": 4}
            count_str = lurking_match.group(1).lower()
            count = word_map.get(count_str, 0)
            if count == 0 and count_str.isdigit(): count = int(count_str)
                
            if count > 0:
                available_mms = [m for m in self.data['masterminds'] if m['name'] != mm['name']]
                if len(available_mms) < count:
                    lurking = available_mms
                else:
                    lurking = random.sample(available_mms, count)
                
                # Store the objects, don't modify the name string here
                self.setup['lurking_masterminds'] = lurking
        # --- 3. TYRANT MASTERMINDS (NEW) ---
        # Matches: "Choose 3 other Masterminds"
        tyrant_match = re.search(r'Choose (\d+) other Masterminds', scheme_text, re.IGNORECASE)
        if tyrant_match:
            count = int(tyrant_match.group(1))
            self.scheme_mods['tyrant_masterminds_count'] = count
            
            # Exclude Main Mastermind
            used_names = [self.setup['mastermind']['name']]
            # Exclude Lurking if they exist
            if self.setup.get('lurking_masterminds'):
                used_names.extend([m['name'] for m in self.setup['lurking_masterminds']])
            
            # Find available
            available = [m for m in self.data['masterminds'] if m['name'] not in used_names]
            
            if len(available) >= count:
                self.setup['tyrant_masterminds'] = random.sample(available, count)
            else:
                self.setup['tyrant_masterminds'] = available
                print(f"   [!] Warning: Not enough Masterminds left for Tyrants (Needed {count}).")  

        # --- 4. DRAINED MASTERMIND (NEW) ---
        if self.scheme_mods.get('drained_mastermind_required'):
            used_names = [self.setup['mastermind']['name']]
            if self.setup.get('lurking_masterminds'):
                used_names.extend([m['name'] for m in self.setup['lurking_masterminds']])
            if self.setup.get('tyrant_masterminds'):
                used_names.extend([m['name'] for m in self.setup['tyrant_masterminds']])
            
            available = [m for m in self.data['masterminds'] if m['name'] not in used_names]
            
            if available:
                drained = random.choice(available)
                self.setup['drained_mastermind'] = drained
                
                # Handle "Always Leads" Requirement
                lead_group = drained.get('always_leads')
                if lead_group and lead_group != 'Unknown':
                    # Try to find it in Villains
                    v_obj = self._find_group_by_name(lead_group, 'villains')
                    if v_obj:
                        self.scheme_mods['required_villains'].append(v_obj['group_name'])
                    else:
                        # Try Henchmen (rare, but possible)
                        h_obj = self._find_group_by_name(lead_group, 'henchmen')
                        if h_obj:
                            self.scheme_mods['required_henchmen'].append(h_obj['name'])
            else:
                 print("   [!] Warning: No Masterminds left for Drained Mastermind.")
        
    def pick_villains_and_henchmen(self):
        base = SETUP_RULES.get(self.player_count, SETUP_RULES[2])
        
        # --- VILLAINS ---
        total_villains_needed = base['villains'] + self.scheme_mods['extra_villains']
        selected_villains = []
        
        # A. SCHEME REQUIREMENTS (PRIORITY 1)
        for req_name in self.scheme_mods['required_villains']:
            found = self._find_group_by_name(req_name, 'villains')
            if found and found not in selected_villains:
                selected_villains.append(found)

        # B. MASTERMIND LEAD (PRIORITY 2 - Only if slots available)
        always_leads = self.setup['mastermind'].get('always_leads', 'Unknown')
        if always_leads != 'Unknown':
            # Check if we have space left for the Mastermind's preference
            if len(selected_villains) < total_villains_needed:
                # 1. Search Villains (Standard + Text Scanning)
                sorted_villains = sorted(self.data['villains'], key=lambda x: len(x.get('name') or x.get('group_name') or ''), reverse=True)
                for v in sorted_villains:
                    v_name = v.get('name') or v.get('group_name')
                    if v_name and v_name.lower() in always_leads.lower():
                        if v not in selected_villains:
                            selected_villains.append(v)
                        if "and" not in always_leads.lower(): break
            
            # Check Henchmen (We handle this here to capture the requirement, actual add happens below)
            # Note: Schemes usually dictate Henchmen strictly (1 group). 
            # If Scheme didn't force one, we let Mastermind lead.
            # 2. Search Henchmen (Standard + Text Scanning)
            sorted_hench = sorted(self.data['henchmen'], key=lambda x: len(x.get('name') or x.get('group_name') or ''), reverse=True)
            for h in sorted_hench:
                h_name = h.get('name') or h.get('group_name')
                if h_name and h_name.lower() in always_leads.lower():
                    if h_name not in self.scheme_mods['required_henchmen']:
                        self.scheme_mods['required_henchmen'].append(h_name)
            
            # 3. Search Henchmen (Generic "A Shi'ar Henchman")
            generic_match = re.search(r'(?:a|an|the) ([a-zA-Z0-9\-\']+) Henchm[ae]n', always_leads, re.IGNORECASE)
            if generic_match:
                descriptor = generic_match.group(1)
                candidates = [h for h in self.data['henchmen'] 
                              if descriptor.lower() in (h.get('name') or h.get('group_name') or '').lower()]
                if candidates:
                    chosen = random.choice(candidates)
                    c_name = chosen.get('name') or chosen.get('group_name')
                    if c_name not in self.scheme_mods['required_henchmen']:
                         self.scheme_mods['required_henchmen'].append(c_name)

        # C. FILL RANDOM VILLAINS
        target_count = max(total_villains_needed, len(selected_villains))
        remaining = target_count - len(selected_villains)
        
        if remaining > 0:
            # Filter available villains to exclude those already selected AND those banned
            available = [
                v for v in self.data['villains'] 
                if v not in selected_villains
                and not any(b.lower() in (v.get('group_name') or v.get('name') or '').lower() for b in self.scheme_mods['banned_villains'])
            ]
            
            if len(available) >= remaining:
                selected_villains.extend(random.sample(available, remaining))
            else:
                print(f"   [!] Warning: Not enough Villains left to fill deck (Need {remaining}, Found {len(available)}).")
                selected_villains.extend(available)
            
        self.setup['villains'] = selected_villains
        for v in selected_villains: self.synergy_tags.extend(self._get_tags(v))

        # --- HENCHMEN ---
        total_hench_needed = base['henchmen'] + self.scheme_mods['extra_henchmen']
        selected_hench = []

        # A. SCHEME REQUIREMENTS (PRIORITY 1)
        for req_name in self.scheme_mods['required_henchmen']:
            found = self._find_group_by_name(req_name, 'henchmen')
            if found and found not in selected_hench:
                selected_hench.append(found)
        
        # B. MASTERMIND LEAD (PRIORITY 2 - Implied by list population above)
        # Note: In the block above, we added MM leads to 'required_henchmen' list. 
        # However, if Scheme ALREADY filled the list (e.g. 1 slot needed, Scheme took 1),
        # we must ensure we don't go over limit unless "Extra" was triggered.
        
        # We enforce the limit here simply by respecting 'total_hench_needed'.
        # If 'required_henchmen' has 2 items (1 Scheme, 1 MM) but we only need 1,
        # we slice the list or rely on the loop order. 
        # Since we append Scheme items first in the loop above, they naturally win if we truncate.
        
        # C. FILL RANDOM HENCHMEN
        # Only fill if we haven't hit the cap
        if len(selected_hench) > total_hench_needed:
            selected_hench = selected_hench[:total_hench_needed]

        target_count_h = max(total_hench_needed, len(selected_hench))
        remaining_h = target_count_h - len(selected_hench)
        
        if remaining_h > 0:
            # Filter available henchmen to exclude selected AND banned
            available = [
                h for h in self.data['henchmen'] 
                if h not in selected_hench
                and not any(b.lower() in (h.get('name') or h.get('group_name') or '').lower() for b in self.scheme_mods['banned_henchmen'])
            ]
            
            if len(available) >= remaining_h:
                selected_hench.extend(random.sample(available, remaining_h))
            else:
                print(f"   [!] Warning: Not enough Henchmen left (Need {remaining_h}, Found {len(available)}).")
                selected_hench.extend(available)
            
        self.setup['henchmen'] = selected_hench
        
    def _find_hero_by_name(self, name_fragment):
        """Fuzzy search for a Hero."""
        # 1. Exact Match
        for h in self.data['heroes']:
            if h.get('hero', '').lower() == name_fragment.lower(): return h
            
        # 2. Contains Match
        for h in self.data['heroes']:
            if name_fragment.lower() in h.get('hero', '').lower(): return h
        return None
    def pick_heroes(self):
        hero_slots = 5
        deck = []
        
        # --- PRE-FILL PLAYER CHOICES (NEW) ---
        # Insert placeholders for player choices. 
        # The main loop (while len(deck) < hero_slots) will naturally fill only the remaining slots.
        if self.scheme_mods.get('player_picked_heroes', 0) > 0:
            for i in range(self.scheme_mods['player_picked_heroes']):
                deck.append({
                    "hero": f"CHOSEN BY PLAYER {i+1}",
                    "set": "Player Choice",
                    "team": "Any",
                    "is_placeholder": True  # Flag for formatting later
                })
       
        if not self.data.get('heroes'): raise Exception("No Heroes found.")
        available_heroes = [
            h for h in self.data['heroes'] 
            if h['hero'] not in self.scheme_mods['banned_heroes']
        ]
        
        # --- HANDLE SPECIFIC HERO INCLUSIONS (FIXED) ---
        for req in self.scheme_mods['required_hero_deck_includes']:
            req_name = req['name'].lower()
            # Handle "Wolverine or Logan" logic
            search_terms = [t.strip() for t in req_name.split(' or ')]
            
            # Find all candidates matching ANY of the search terms
            candidates = []
            for h in available_heroes:
                h_name = h['hero'].lower()
                if any(term in h_name for term in search_terms):
                    candidates.append(h)
            
            needed = req['count']
            
            # If we found enough candidates, pick them
            if len(candidates) >= needed:
                chosen = random.sample(candidates, needed)
                deck.extend(chosen)
                
                # FIX: Remove ALL candidates from pool to enforce "Exactly" exclusivity
                # This ensures we don't randomly pick a 2nd Wolverine later.
                for h in candidates:
                    if h in available_heroes: available_heroes.remove(h)
            else:
                print(f"   [!] Warning: Not enough heroes matching '{req['name']}'. Found {len(candidates)}, needed {needed}.")
                deck.extend(candidates)
                for h in candidates:
                    if h in available_heroes: available_heroes.remove(h)

        # --- HANDLE REQUIRED TEAMS (FIXED) ---
        for req in self.scheme_mods.get('required_teams', []):
            target_team = req['team']
            
            # Find candidates belonging to the required team
            # FIX: Use self._get_hero_team(h) instead of h.get('team') because the team info is nested.
            candidates = [
                h for h in available_heroes 
                if target_team in self._get_hero_team(h).lower()
            ]
            
            needed = req['count']
            
            if len(candidates) >= needed:
                chosen = random.sample(candidates, needed)
                deck.extend(chosen)
                # Remove from pool
                for h in chosen:
                    if h in available_heroes: available_heroes.remove(h)
            else:
                # Fallback if not enough heroes of that team exist in user's collection
                print(f"   [!] Warning: Not enough heroes for team '{target_team}'. Needed {needed}, found {len(candidates)}.")
                deck.extend(candidates)
                for h in candidates:
                    if h in available_heroes: available_heroes.remove(h)

        # --- A. HANDLE TEAM VERSUS SETUP (NEW) ---
        if self.scheme_mods['team_versus_counts']:
            count_a, count_b = self.scheme_mods['team_versus_counts']
            
            # Group all available heroes by Team
            teams = {}
            for h in available_heroes:
                t = self._get_hero_team(h)
                if t == 'Unknown': continue
                if t not in teams: teams[t] = []
                teams[t].append(h)
            
            # Find teams with enough heroes to satisfy the requirement
            valid_teams_a = [t for t, heroes in teams.items() if len(heroes) >= count_a]
            
            if len(valid_teams_a) >= 2:
                # Pick Team 1
                team_a_name = random.choice(valid_teams_a)
                heroes_a = random.sample(teams[team_a_name], count_a)
                
                # Pick Team 2 (Must be different)
                valid_teams_b = [t for t in valid_teams_a if t != team_a_name and len(teams[t]) >= count_b]
                if valid_teams_b:
                    team_b_name = random.choice(valid_teams_b)
                    heroes_b = random.sample(teams[team_b_name], count_b)
                    
                    # Commit to Deck
                    deck = heroes_a + heroes_b
                    # Remove chosen heroes from pool to prevent duplicates later
                    for h in deck: 
                        if h in available_heroes: available_heroes.remove(h)
                        
        # --- C. FILTER BANNED TEAMS FROM OPEN SELECTION (NEW) ---
        # This ensures that for "House of M", the remaining slots generally CANNOT be X-Men
        if self.scheme_mods.get('banned_teams_from_open_selection'):
            available_heroes = [
                h for h in available_heroes 
                if self._get_hero_team(h).lower() not in self.scheme_mods['banned_teams_from_open_selection']
            ]
        
        # --- B. STANDARD SELECTION LOOP (Only runs if deck isn't full yet) ---
        # Use the target count from scheme (defaults to 5, but Versus might set it to 6)
        target_count = self.scheme_mods['hero_deck_count']
        
        def score_hero(hero):
            # ... (Paste your existing score_hero function here) ...
            score = 0
            hero_tags = self._get_hero_tags(hero)
            for tag in self.synergy_tags:
                if "Problem_" in tag:
                    keyword = tag.split('_')[-1]
                    if any(keyword in t for t in hero_tags if "Solution" in t or "Mechanic" in t):
                        score += 5
            current_teams = [self._get_hero_team(h) for h in deck]
            my_team = self._get_hero_team(hero)
            if my_team in current_teams and my_team != 'Unknown': score += 3
            for h_existing in deck:
                if h_existing.get('is_placeholder'):
                    continue
                existing_tags = self._get_hero_tags(h_existing)
                my_classes = [t for t in hero_tags if "Class_" in t and "Need" not in t]
                their_needs = [t for t in existing_tags if "Need_Class_" in t]
                my_needs = [t for t in hero_tags if "Need_Class_" in t]
                their_classes = [t for t in existing_tags if "Class_" in t and "Need" not in t]
                for need in their_needs:
                    if need.replace("Need_", "") in my_classes: score += 2
                for need in my_needs:
                    if need.replace("Need_", "") in their_classes: score += 2
            return score

        # Only run loop if we didn't already fill the deck with Versus logic
        while len(deck) < target_count and available_heroes:
            sample_size = min(3, len(available_heroes))
            candidates = random.sample(available_heroes, sample_size)
            best_candidate = max(candidates, key=score_hero)
            deck.append(best_candidate)
            available_heroes.remove(best_candidate)
            
        self.setup['heroes'] = deck
        
        # --- Pick separate heroes for the Villain Deck (UPDATED) ---
        self.setup['villain_deck_heroes'] = []
        
        # 1. Process Specific Requirements (e.g. Jean Grey)
        for req_name in self.scheme_mods['required_villain_deck_heroes']:
            found = self._find_hero_by_name(req_name)
            if found:
                self.setup['villain_deck_heroes'].append(found)
                # Remove from available so we don't pick it again for the Hero Deck
                if found in available_heroes:
                    available_heroes.remove(found)
            else:
                print(f"   [!] Warning: Could not find required hero '{req_name}' in your sets.")
                # Fallback to random if specific one is missing
                if available_heroes:
                    fallback = random.choice(available_heroes)
                    self.setup['villain_deck_heroes'].append(fallback)
                    available_heroes.remove(fallback)

        # 2. Fill remaining generic slots
        filled_count = len(self.setup['villain_deck_heroes'])
        needed_count = self.scheme_mods['villain_deck_heroes']
        remaining = needed_count - filled_count
        
        if remaining > 0:
            if len(available_heroes) >= remaining:
                extras = random.sample(available_heroes, remaining)
                self.setup['villain_deck_heroes'].extend(extras)
            else:
                print("[!] Warning: Not enough heroes left for Villain Deck!")

    def generate_setup(self):
        print("4. Generating...")
        if not self.load_data(): return None
        
        self.pick_scheme()
        self.pick_mastermind()
        
        # --- CHECK FOR MASTERMIND-SPECIFIC TWIST OVERRIDES (NEW) ---
        # Checks for rules like: "If using Lilith: Use 1 Twist total"
        scheme_text = " ".join(self.setup['special_rules'])
        cond_twist_match = re.search(r'If using (.*?): Use (\d+) Twists? total', scheme_text, re.IGNORECASE)
        
        if cond_twist_match:
            req_mm_name = cond_twist_match.group(1).strip()
            req_twist_count = int(cond_twist_match.group(2))
            
            # Fuzzy match: Check if the required name is part of the current Mastermind's name
            # e.g. "Lilith" matches "Lilith, Mother of Demons"
            current_mm = self.setup['mastermind']['name']
            
            if req_mm_name.lower() in current_mm.lower() or current_mm.lower() in req_mm_name.lower():
                self.scheme_mods['twists'] = req_twist_count
                self.scheme_mods['twist_note'] = f"(If using {req_mm_name})"
                print(f"   [!] Applied Mastermind Override: {req_twist_count} Twists for {current_mm}")
        
        self.pick_villains_and_henchmen()
        self.pick_heroes()
        
        base_bystanders = SETUP_RULES.get(self.player_count, SETUP_RULES[2])['bystanders']
        if self.scheme_mods['bystanders_override'] is not None:
            final_bystanders = self.scheme_mods['bystanders_override']
        else:
            final_bystanders = base_bystanders + self.scheme_mods['bystanders_add']
        
        # --- FORMAT MASTERMIND STRING ---
        mm_display = f"{self.setup['mastermind']['name']} ({self.setup['mastermind']['set']})"
        if self.setup.get('lurking_masterminds'):
            l_names = [f"{m['name']} ({m['set']})" for m in self.setup['lurking_masterminds']]
            mm_display += f"\n  (Lurking: {', '.join(l_names)})"

        # --- PICK HENCHMEN FOR HERO DECK (NEW) ---
        if self.scheme_mods['henchmen_in_hero_deck_count'] > 0:
            # Get names of Henchmen already used in the Villain Deck
            used_henchmen_names = [h['name'] for h in self.setup.get('henchmen', [])]
            
            # Find available Henchmen (excluding those used)
            candidates = [h for h in self.data['henchmen'] if h['name'] not in used_henchmen_names]
            
            if candidates:
                chosen = random.choice(candidates)
                self.scheme_mods['henchmen_in_hero_deck_obj'] = chosen
            else:
                print("   [!] Warning: No unique Henchmen groups left for Hero Deck.")
                
       # Helper to format Henchmen list with Alias
        final_henchmen_list = []
        for i, h in enumerate(self.setup['henchmen']):
            display_name = f"{h['name']} ({h['set']})"
            # Apply alias to the LAST group if an alias is defined (Standard for 'Extra' groups)
            if self.scheme_mods['henchman_alias'] and i == len(self.setup['henchmen']) - 1:
                # CHANGED: Now displays "Real Name (Set) (as Alias)"
                display_name = f"{display_name} (as {self.scheme_mods['henchman_alias']})"
            final_henchmen_list.append(display_name)
            
        vd_heroes_formatted = []
        for h in self.setup.get('villain_deck_heroes', []):
            h_str = f"{h['hero']} ({self._get_hero_team(h)} - {h['set']})"
            
            # If a specific quantity rule (like "8 random cards") was found, append it
            # We assume this applies to the random/extra heroes
            if self.scheme_mods.get('extra_hero_card_count'):
                h_str += f" ({self.scheme_mods['extra_hero_card_count']} random cards)"
            
            vd_heroes_formatted.append(h_str)

        result = {
            "Mastermind": f"{self.setup['mastermind']['name']} ({self.setup['mastermind']['set']})",
            # We now pass the raw list for better UI handling
            "Lurking_Masterminds": [f"{m['name']} ({m['set']})" for m in self.setup.get('lurking_masterminds', [])],
            "Scheme": f"{self.setup['scheme']['name']} ({self.setup['scheme']['set']})",
            "Scheme_Description": self.setup['special_rules'],
            "Villains": [f"{v['group_name']} ({v['set']})" for v in self.setup['villains']],
            "Henchmen": final_henchmen_list,
            "Heroes": [
                h['hero'] if h.get('is_placeholder') 
                else f"{h['hero']} ({self._get_hero_team(h)} - {h['set']})" 
                for h in self.setup['heroes']
            ] + \
            ([f"{self.scheme_mods['bystanders_in_hero_deck']} Bystanders"] if self.scheme_mods['bystanders_in_hero_deck'] > 0 else []) + \
            ([f"{self.scheme_mods['henchmen_in_hero_deck_count']} {self.scheme_mods['henchmen_in_hero_deck_obj']['name']} (Henchmen - {self.scheme_mods['henchmen_in_hero_deck_obj']['set']})"] if self.scheme_mods['henchmen_in_hero_deck_obj'] else []),
            "Villain_Deck_Heroes": vd_heroes_formatted,
            "Wedding_Heroes": [f"{h['hero']} ({h['set']})" for h in self.scheme_mods.get('wedding_heroes', [])],
            "Custom_Deck": self.scheme_mods.get('custom_deck'),
            "Tyrant_Masterminds": [f"{m['name']} ({m['set']})" for m in self.setup.get('tyrant_masterminds', [])],
            "Drained_Mastermind": self.setup.get('drained_mastermind'),
            "Villain_Deck_Setup": {
                "Master_Strikes": self.scheme_mods['master_strikes'],
                "Scheme_Twists": f"{self.scheme_mods['twists']} {self.scheme_mods['twist_note']}",
                "Bystanders": final_bystanders,
                "Heroes_from_Hero_Deck": self.scheme_mods['heroes_from_hero_deck'],
                "Sidekicks": self.scheme_mods['sidekicks_in_villain_deck'],
                "Ambitions": self.scheme_mods['ambitions_in_villain_deck'],
                "Officers": self.scheme_mods['officers_in_villain_deck'],
                "Tactics": self.scheme_mods['tactics_in_villain_deck'],
                "Quantum_Ambush": self.scheme_mods['quantum_ambush_scheme']
            }
        }
        return result

# ==========================================
# STREAMLIT UI CODE
# ==========================================

def main():
    st.set_page_config(page_title="Legendary Randomizer", page_icon="🦸", layout="wide")

    # --- Sidebar: Configuration ---
    st.sidebar.header("⚙️ Setup")
    
    # 1. Player Count
    players = st.sidebar.slider("Number of Players", min_value=1, max_value=5, value=3)

    # 2. Set Selection
    # List all your sets here. You can also load this dynamically from your JSON if you want.
    all_sets = []
    try:
        # Load unique sets directly from the heroes file
        with open("enriched_heroes.json", "r", encoding="utf-8") as f:
            heroes_data = json.load(f)
            # Create a sorted list of unique set names
            all_sets = sorted(list({h.get("set") for h in heroes_data if h.get("set")}))
            
    except Exception as e:
        st.error(f"⚠️ Error loading sets from enriched_heroes.json: {e}")
        all_sets = ["Core Set"] # Fallback if file is missing/broken

    # Smart Defaults: Only select defaults if they actually exist in the loaded list
    desired_defaults = ["Core Set", "Marvel Studios' What If...?"]
    default_sets = [s for s in desired_defaults if s in all_sets]
    
    # If defaults are missing, just pick the first available set to avoid empty selection errors
    if not default_sets and all_sets:
        default_sets = [all_sets[0]]

    selected_sets = st.sidebar.multiselect("Select Expansions", all_sets, default=default_sets)

    # --- Main Area ---
    st.title("🦸 Legendary Setup Randomizer")
    
    if st.button("🎲 Generate New Setup", type="primary", use_container_width=True):
        if not selected_sets:
            st.error("Please select at least one expansion set.")
        else:
            run_randomizer(selected_sets, players)

def run_randomizer(selected_sets, players):
    # Initialize your class
    # We use st.spinner to show loading state
    with st.spinner('Consulting the Multiverse...'):
        try:
            randomizer = LegendaryRandomizer(selected_sets, players)
            setup = randomizer.generate_setup()
            
            if setup:
                display_results(setup)
            else:
                st.error("Failed to generate setup. Check your data files.")
        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.code(traceback.format_exc())

def display_results(setup):
    # --- 1. Mastermind & Scheme ---
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🦹 Mastermind")
        st.info(f"**{setup['Mastermind']}**")
        
        # Lurking Masterminds (Now separate!)
        if setup.get('Lurking_Masterminds'):
            st.markdown("**👥 Lurking Masterminds:**")
            for lm in setup['Lurking_Masterminds']:
                st.caption(f"- {lm}")

        # Drained Mastermind
        if setup.get('Drained_Mastermind'):
            dm = setup['Drained_Mastermind']
            st.markdown(f"**🔻 Drained Mastermind:**")
            st.caption(f"{dm['name']} ({dm['set']}) *(Set aside, out of play)*")
        
        # Tyrant Masterminds
        if setup.get('Tyrant_Masterminds'):
            st.markdown("**👑 Tyrant Masterminds:**")
            for tm in setup['Tyrant_Masterminds']:
                st.caption(f"- {tm}")

    with col2:
        st.subheader("📜 Scheme")
        st.warning(f"**{setup['Scheme']}**")
        
        # Custom Decks (Moved here for visibility)
        if setup.get('Custom_Deck'):
            cd = setup['Custom_Deck']
            st.markdown(f"**📦 {cd['name']} Content:**")
            for line in cd['lines']:
                st.error(f"- {line}")

    st.divider()

    # --- 2. Villains & Henchmen ---
    col3, col4 = st.columns(2)
    with col3:
        st.write("### 😈 Villains")
        for v in setup['Villains']:
            st.write(f"- {v}")
            
    with col4:
        st.write("### 🤖 Henchmen")
        for h in setup['Henchmen']:
            st.write(f"- {h}")

    st.divider()

    # --- 3. Heroes ---
    st.write("### 🦸 Heroes")
    hero_cols = st.columns(3)
    for i, h in enumerate(setup['Heroes']):
        with hero_cols[i % 3]:
            st.success(h)
            
    # Wedding Heroes
    if setup.get('Wedding_Heroes'):
        st.write("#### 💍 Wedding Heroes (Set Aside)")
        for wh in setup['Wedding_Heroes']:
             st.info(f"- {wh}")

    st.divider()

    # --- 4. Villain Deck Composition ---
    st.write("### 🃏 Villain Deck Composition")
    
    vd = setup['Villain_Deck_Setup']
    
    # Standard Counts
    m1, m2, m3 = st.columns(3)
    m1.metric("Scheme Twists", vd['Scheme_Twists'])
    m2.metric("Master Strikes", vd['Master_Strikes'])
    m3.metric("Bystanders", vd['Bystanders'])

    st.markdown("#### ➕ Required Extras")
    
    # 1. Extra Cards (Sidekicks, Officers, etc.)
    extras_cols = st.columns(2)
    with extras_cols[0]:
        if vd.get('Sidekicks'): st.write(f"**Sidekicks:** {vd['Sidekicks']}")
        if vd.get('Ambitions'): st.write(f"**Ambitions:** {vd['Ambitions']}")
        if vd.get('Officers'): st.write(f"**S.H.I.E.L.D. Officers:** {vd['Officers']}")
        if vd.get('Heroes_from_Hero_Deck'): st.write(f"**Cards from Hero Deck:** {vd['Heroes_from_Hero_Deck']} (Random)")
        
    with extras_cols[1]:
        if vd.get('Tactics'): st.write(f"**Mastermind Tactics:** {vd['Tactics']}")
        if vd.get('Quantum_Ambush'): st.write("**Ambush Scheme:** Yes")

    # 2. Specific Extra Heroes
    if setup['Villain_Deck_Heroes']:
        st.markdown("**🦸 Extra Heroes in Villain Deck:**")
        for h in setup['Villain_Deck_Heroes']:
            st.markdown(f"- {h}")

    st.divider()

    # --- 5. Special Rules ---
    with st.expander("📝 Setup Notes & Special Rules", expanded=False):
        for line in setup['Scheme_Description']:
            if "Setup" in line or "Special Rules" in line:
                st.markdown(f"* {line}")

if __name__ == "__main__":
    main()
