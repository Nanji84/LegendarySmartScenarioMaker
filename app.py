import streamlit as st
import json
import random
import re
import os
import traceback
import uuid
import datetime

# TOGGLE THIS TO TRUE/FALSE TO SHOW/HIDE SYNERGY LOGS
SHOW_SYNERGY_DEBUG = True

HISTORY_FILE = "scenario_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            pass
    return []

def save_history(history):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        pass

def add_to_history(setup, players, selected_sets):
    history = load_history()
    entry = {
        "id": uuid.uuid4().hex,
        "timestamp": datetime.datetime.now().isoformat(),
        "players": players,
        "selected_sets": list(selected_sets),
        "setup": setup
    }
    history.insert(0, entry)
    history = history[:50]
    save_history(history)

def delete_from_history(entry_id):
    history = load_history()
    history = [e for e in history if e.get('id') != entry_id]
    save_history(history)

SETUP_RULES = {
    1: {"villains": 1, "henchmen": 1, "bystanders": 1, "heroes": 5},
    2: {"villains": 2, "henchmen": 1, "bystanders": 2, "heroes": 5},
    3: {"villains": 3, "henchmen": 1, "bystanders": 8, "heroes": 5},
    4: {"villains": 3, "henchmen": 2, "bystanders": 8, "heroes": 5},
    5: {"villains": 4, "henchmen": 2, "bystanders": 12, "heroes": 6}
}

DEFAULT_SYNERGY_CONFIG = {
    "weights": {
        "enemy_counter_class": 3.0,
        "enemy_counter_team": 3.0,
        "team_requirement_match": 4.0,
        "team_simple_match": 0.5,
        "class_trigger_deck": 3.0,
        "class_triggered_by_deck": 3.0,
        "class_simple_match": 1.0,
        "curve_balanced_starter": 2.0,
        "curve_fixer_cheap": 4.0,
        "curve_penalty_expensive": -2.0,
        "curve_fixer_heavy": 3.0,
        "curve_normal": 1.0
    },
    "setup_to_hero_rules": [
        {
            "trigger_tag": "Mechanic_Wound",
            "matching_tags": ["Solution_Heal_Wound"],
            "keywords": ["heal", "remove a wound", "remove wounds"],
            "weight": 2.0,
            "display_name": "Wound Management"
        },
        {
            "trigger_tag": "Mechanic_Rescue",
            "matching_tags": ["Mechanic_Rescue_Bystander", "Problem_Capture_Bystander"],
            "keywords": ["bystander", "rescue"],
            "weight": 4.0,
            "display_name": "Bystander Rescue"
        },
        {
            "trigger_tag": "Mechanic_Artifact",
            "matching_tags": ["Type_Artifact"],
            "keywords": ["artifact"],
            "weight": 5.0,
            "display_name": "Artifact Synergy"
        },
        {
            "trigger_tag": "Gen_KO",
            "matching_tags": ["Gen_KO"],
            "keywords": ["ko "],
            "weight": 2.0,
            "display_name": "KO/Thinning"
        },
        {
            "trigger_tag": "Mechanic_Rise_Dead",
            "matching_tags": ["Mechanic_Rise_Dead"],
            "keywords": ["ko pile", "discard pile"],
            "weight": 3.0,
            "display_name": "Graveyard Interaction"
        }
    ],
    "hero_to_hero_rules": [
        {
            "type": "tag_cross_count",
            "synergy_tag": "Mechanic_Cost_2_Or_Less_Synergy",
            "target_tags": ["Cost_0", "Cost_1", "Cost_2", "Cost_2*"],
            "candidate_to_deck_weight": 2.0,
            "deck_to_candidate_weight": 3.0,
            "display_name": "2-Cost Synergy"
        },
        {
            "type": "tag_cross_match",
            "tag_a": "Problem_Give_Wound",
            "tag_b": "Solution_Heal_Wound",
            "weight": 3.0,
            "display_name": "Wound Synergy"
        }
    ]
}


class LegendaryRandomizer:
    def __init__(self, user_sets, player_count, user_selections=None):
        self.user_sets = [s.lower().strip() for s in user_sets]
        self.player_count = player_count
        self.user_selections = user_selections or {}  # <--- NEW: Store selections
        
        # Load synergy configuration
        self.synergy_config = DEFAULT_SYNERGY_CONFIG
        config_path = "synergy_config.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.synergy_config = json.load(f)
                print(f"Loaded synergy configuration from {config_path}")
            except Exception as e:
                print(f"Warning: Failed to parse {config_path}. Using default configuration. Error: {e}")
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
            # Dynamically set base hero count (5 for 1-4p, 6 for 5p)
            "hero_deck_count": SETUP_RULES[player_count]["heroes"],
            "villain_deck_heroes": 0,
            "required_villain_deck_heroes": [],
            "heroes_from_hero_deck": 0, 
            "team_versus_counts": None,
            "custom_deck": None,    
            "banned_heroes": [],     
            "required_hero_deck_includes": [],
            "bystanders_in_hero_deck": 0,
            "tyrant_masterminds_count": 0,
            "sidekicks_in_villain_deck": 0,
            "ambitions_in_villain_deck": 0,
            "officers_in_villain_deck": 0,
            "player_picked_heroes": 0,
            "required_teams": [],
            "henchmen_in_hero_deck_count": 0, 
            "henchmen_in_hero_deck_obj": None, 
            "banned_villains": [],
            "banned_henchmen": [],
            "tactics_in_villain_deck": 0,
            "quantum_ambush_scheme": False,
            "henchman_alias": None,
            "wedding_heroes": [],
            "banned_teams_from_open_selection": [],
            "drained_mastermind_required": False,
            "extra_hero_card_count": None,
            "double_group_count": False,
            "half_deck_mechanic": False
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
            
            # F. X + Players (Phrasing 2 - NEW): "Twists equal to 5 plus the number of players"
            base_plus_players_match = re.search(r'Twists equal to (\d+) plus (?:the )?number of players', text, re.IGNORECASE)

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
                
            elif base_plus_players_match:  # <--- NEW LOGIC
                base = int(base_plus_players_match.group(1))
                self.scheme_mods['twists'] = base + self.player_count
                self.scheme_mods['twist_note'] = f"({base} + {self.player_count} players)"
                
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

        # --- 3. BYSTANDERS (FIXED) ---
        if re.search(r'no Bystanders', text, re.IGNORECASE):
            self.scheme_mods['bystanders_override'] = 0
        else:
            # 1. Total Override ("8 total Bystanders")
            total_bys = re.search(r'(\d+)\s+total\s+Bystanders', text, re.IGNORECASE)
            if total_bys:
                self.scheme_mods['bystanders_override'] = int(total_bys.group(1))
            
            # 2. Additive Logic (Sentence-by-sentence check)
            # We split by sentences to ensure we catch conditions like "1-2 players: Add 3."
            sentences = re.split(r'[.()\n]', text)
            for s in sentences:
                s = s.strip()
                if not s: continue
                
                # Check if this sentence adds Bystanders
                add_match = re.search(r'Add\s+(\d+)\s+(?:extra\s+)?Bystanders', s, re.IGNORECASE)
                if add_match:
                    val = int(add_match.group(1))
                    
                    # Check for Player Constraint at the start of the sentence
                    # Matches: "1-2 Players:", "For 3 players:", "If 5 players"
                    p_match = re.search(r'^(?:(?:For|If)\s+)?(?:only\s+)?([0-9\s\-or]+)\s+players?', s, re.IGNORECASE)
                    
                    if p_match:
                        condition_str = p_match.group(1).strip()
                        is_match = False
                        
                        # Range Check (e.g. "1-2")
                        if '-' in condition_str:
                            parts = condition_str.split('-')
                            if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                                low, high = int(parts[0]), int(parts[1])
                                if low <= self.player_count <= high: is_match = True
                        # List Check (e.g. "2", "2 or 3")
                        else:
                            nums = [int(n) for n in re.findall(r'\d+', condition_str)]
                            if self.player_count in nums: is_match = True
                            
                        # If constraint exists and is NOT met, skip this addition
                        if not is_match:
                            continue 
                            
                    # If no constraint found, OR constraint met, add the value
                    self.scheme_mods['bystanders_add'] += val

        # --- 4. HERO DECK SIZE (FIXED v4) ---
        # Split on '.', '(', ')', or newlines to separate rules so we process them individually
        sentences = re.split(r'[.()\n]', text)
        explicit_found = False
        
        for s in sentences:
            s = s.strip()
            if not s: continue

            # 1. PLAYER CONSTRAINT CHECK
            # If a sentence starts with "For X players" or "If X players", we verify the count.
            # If the player count DOES NOT match, we SKIP this sentence entirely.
            # This prevents "If 2 players: Use 4 Heroes" from triggering on 3 players.
            p_match = re.search(r'^(?:For|If) (?:only )?([0-9\s\-or]+) players?', s, re.IGNORECASE)
            if p_match:
                condition_str = p_match.group(1)
                is_match = False
                # Parse Range (e.g. "2-3")
                if '-' in condition_str:
                    parts = condition_str.split('-')
                    if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                        low, high = int(parts[0]), int(parts[1])
                        if low <= self.player_count <= high: is_match = True
                # Parse List (e.g. "2", "2 or 3")
                else:
                    nums = [int(n) for n in re.findall(r'\d+', condition_str)]
                    if self.player_count in nums: is_match = True
                
                if not is_match:
                    continue # Skip this sentence

            # 2. CHECK FOR ADDITIVE RULES ("Add another Hero", "Add 1 extra Hero")
            # We explicitly exclude "to/into the Villain Deck" to avoid "Add 8 random cards... to the Villain Deck"
            add_match = re.search(r'Add\s+(?:an|another|(\d+)|(one|two|three))\s+(?:extra\s+)?Hero(?:es)?(?!\s+(?:to|into|in)\s+(?:the\s+)?Villain Deck)', s, re.IGNORECASE)
            
            # 3. CHECK FOR BASE COUNT RULES ("Use 5 Heroes", "6 Heroes", "Hero Deck is 4 Heroes")
            # We look for "N Heroes" but use Lookbehind/Lookahead to ensure it's not a shuffle/move rule.
            # (?<!Shuffle\s) -> Not preceded by "Shuffle "
            # (?!\s+(?:from|to|into)) -> Not followed by " from", " to", " into"
            # This correctly matches "6 Heroes" but ignores "Shuffle 12 Heroes from..."
            base_match = re.search(r'(?<!Shuffle\s)(?<!Reveal\s)(?<!Look\s)(?<!Add\s)(?<!\d-)(?<!\d\s)(\d+)\s+Heroes(?!\s+(?:from|to|into))', s, re.IGNORECASE)
            
            if add_match:
                to_add = 1
                if add_match.group(1): # Digit (e.g. "2")
                    to_add = int(add_match.group(1))
                elif add_match.group(2): # Word (e.g. "two")
                    word_map = {"one": 1, "two": 2, "three": 3}
                    to_add = word_map.get(add_match.group(2).lower(), 1)
                
                # If we haven't found a base count yet, start at standard 5 before adding
                if self.scheme_mods['hero_deck_count'] == 5 and not explicit_found:
                     pass 
                
                self.scheme_mods['hero_deck_count'] += to_add

            elif base_match:
                val = int(base_match.group(1))
                
                # Safety: Ignore values >= 10 unless explicitly saying "Hero Deck" 
                # (Prevents accidents with "Shuffle 14 cards")
                is_explicit = "hero deck" in s.lower()
                if val >= 10 and not is_explicit: 
                    continue 

                self.scheme_mods['hero_deck_count'] = val
                explicit_found = True
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
                
        # --- H. ORDERED HERO STACK (NEW) ---
        # Matches: "Put 14 Adam Warlock Hero cards in a face up stack"
        ordered_stack_match = re.search(r'Put (\d+) (.*?) Hero cards in a face up stack', text, re.IGNORECASE)
        if ordered_stack_match:
            count = int(ordered_stack_match.group(1))
            hero_name = ordered_stack_match.group(2).strip()
            
            # 1. Ban this hero from the main Hero Deck so they don't appear twice
            self.scheme_mods['banned_heroes'].append(hero_name)
            
            # 2. Add to Custom Deck display (appears under Scheme description)
            self.scheme_mods['custom_deck'] = {
                "name": f"{hero_name} Stack",
                "lines": [f"{count} cards of {hero_name} (Ordered by cost)"]
            }
        
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
            
        # --- 18. HERO TEAM REQUIREMENTS (FIXED) ---
        # Pattern A: "Use at least 1 [spider-friends] Hero"
        team_req_match = re.search(r'Use at least (\d+) \[?([a-zA-Z0-9\-\s]+)\]? Hero', text, re.IGNORECASE)
        
        # Pattern B: "...including at least one [guardians-of-the-galaxy] Hero" (NEW)
        include_team_match = re.search(r'including at least (one|\d+) \[?([a-zA-Z0-9\-\s]+)\]? Hero', text, re.IGNORECASE)

        if team_req_match:
            count = int(team_req_match.group(1))
            team_name = team_req_match.group(2).strip().lower()
            self.scheme_mods['required_teams'].append({'team': team_name, 'count': count})
            
        elif include_team_match:
            count_str = include_team_match.group(1).lower()
            count = 1 if count_str == 'one' else int(count_str)
            team_name = include_team_match.group(2).strip().lower()
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
        # --- 25. DOUBLE GROUPS / HALF CARDS (NEW) ---
        # Matches: "Use double the normal number of Villain and Henchman Groups"
        if re.search(r'Use double the normal number of Villain and Henchman Groups', text, re.IGNORECASE):
            self.scheme_mods['double_group_count'] = True
            self.scheme_mods['half_deck_mechanic'] = True
            
    def _find_by_ui_name(self, ui_name, item_list, type_key='hero'):
        """Resolves a UI selection string (Name or Name (Set)) to a data object."""
        # Check for Set suffix: "Name (Set)"
        match = re.match(r"(.*?) \((.*?)\)$", ui_name)
        if match:
            target_name = match.group(1)
            target_set = match.group(2)
            for item in item_list:
                # Get item name based on type
                if type_key == 'hero': i_name = item['hero']
                elif type_key == 'villain': i_name = item.get('group_name') or item.get('name')
                else: i_name = item.get('name')
                
                if i_name == target_name and item.get('set') == target_set:
                    return item
        else:
            # Fallback to exact name match (for unique names)
            for item in item_list:
                if type_key == 'hero': i_name = item['hero']
                elif type_key == 'villain': i_name = item.get('group_name') or item.get('name')
                else: i_name = item.get('name')
                
                if i_name == ui_name:
                    return item
        return None

    def pick_scheme(self):
        if not self.data.get('schemes'): raise Exception("No Schemes found.")
        
        # Check Manual Selection
        forced_name = self.user_selections.get('scheme')
        if forced_name and forced_name != "Random":
            # Use helper
            scheme = self._find_by_ui_name(forced_name, self.data['schemes'], 'scheme')
            if not scheme: scheme = random.choice(self.data['schemes'])
        else:
            scheme = random.choice(self.data['schemes'])
            
        self.setup['scheme'] = scheme
        self.synergy_tags.extend(self._get_tags(scheme))
        self.setup['special_rules'] = scheme.get('description', [])
        self.parse_scheme_rules(scheme)

    def pick_mastermind(self):
        if not self.data.get('masterminds'): raise Exception("No Masterminds found.")
        
        # 1. Pick Main Mastermind
        forced_name = self.user_selections.get('mastermind')
        mm = None
        
        if forced_name and forced_name != "Random":
             # Use helper
             mm = self._find_by_ui_name(forced_name, self.data['masterminds'], 'mastermind')
        
        if not mm:
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
        if self.scheme_mods['double_group_count']: total_villains_needed *= 2
            
        selected_villains = []
        user_v_picks = self.user_selections.get('villains', [])
        
        # Helper: Check if a requirement is already met by a user selection
        def is_req_satisfied_by_user(req_name, user_picks):
            # Resolve user strings to check for name matches
            req_clean = req_name.lower().strip()
            for pick in user_picks:
                # Remove "(Set Name)" suffix for comparison
                pick_base = re.sub(r' \((.*?)\)$', '', pick).lower().strip()
                # Check for match (e.g. "Deadpool" in "Deadpool (Mercs)")
                if req_clean == pick_base or req_clean in pick_base or pick_base in req_clean:
                    return True
            return False

        # 1. SCHEME REQUIREMENTS (Updated)
        for req_name in self.scheme_mods['required_villains']:
            # If user already picked a version of this group, skip adding the default one
            if is_req_satisfied_by_user(req_name, user_v_picks):
                continue
                
            found = self._find_group_by_name(req_name, 'villains')
            if found and found not in selected_villains:
                selected_villains.append(found)

        # 2. MASTERMIND LEAD (Updated)
        always_leads = self.setup['mastermind'].get('always_leads', 'Unknown')
        if always_leads != 'Unknown':
             # Check if user satisfied this lead manually
             if not is_req_satisfied_by_user(always_leads, user_v_picks):
                 if len(selected_villains) < total_villains_needed:
                    v_obj = self._find_group_by_name(always_leads, 'villains')
                    if v_obj and v_obj not in selected_villains:
                         # NEW: Check if this group is banned (e.g. set aside for a Custom Deck like Monster Pit)
                         is_banned = any(b.lower() in (v_obj.get('group_name') or v_obj.get('name') or '').lower() for b in self.scheme_mods['banned_villains'])
                         
                         if not is_banned:
                             selected_villains.append(v_obj)
                    
                    # Check Henchmen (add to requirements list if found)
                    h_obj = self._find_group_by_name(always_leads, 'henchmen')
                    if h_obj and h_obj['name'] not in self.scheme_mods['required_henchmen']:
                         # Note: Henchmen bans are checked later in the Henchmen section loop
                         self.scheme_mods['required_henchmen'].append(h_obj['name'])

        # 3. USER SELECTIONS (Priority 3)
        for pick_name in user_v_picks:
            if len(selected_villains) < total_villains_needed:
                found = self._find_by_ui_name(pick_name, self.data['villains'], 'villain')
                if found and found not in selected_villains:
                    is_banned = any(b.lower() in (found.get('group_name') or '').lower() for b in self.scheme_mods['banned_villains'])
                    if not is_banned:
                        selected_villains.append(found)

        # 4. FILL RANDOM
        target_count = max(total_villains_needed, len(selected_villains))
        remaining = target_count - len(selected_villains)
        
        if remaining > 0:
            available = [
                v for v in self.data['villains'] 
                if v not in selected_villains
                and not any(b.lower() in (v.get('group_name') or v.get('name') or '').lower() for b in self.scheme_mods['banned_villains'])
            ]
            if len(available) >= remaining:
                selected_villains.extend(random.sample(available, remaining))
            else:
                selected_villains.extend(available)
            
        self.setup['villains'] = selected_villains
        for v in selected_villains: self.synergy_tags.extend(self._get_tags(v))

        # --- HENCHMEN ---
        total_hench_needed = base['henchmen'] + self.scheme_mods['extra_henchmen']
        if self.scheme_mods['double_group_count']: total_hench_needed *= 2
        
        selected_hench = []
        user_h_picks = self.user_selections.get('henchmen', [])

        # 1. SCHEME REQUIREMENTS (Updated)
        for req_name in self.scheme_mods['required_henchmen']:
            if is_req_satisfied_by_user(req_name, user_h_picks):
                continue
            
            found = self._find_group_by_name(req_name, 'henchmen')
            if found and found not in selected_hench:
                selected_hench.append(found)

        # 2. USER SELECTIONS
        for pick_name in user_h_picks:
            if len(selected_hench) < total_hench_needed:
                found = self._find_by_ui_name(pick_name, self.data['henchmen'], 'henchman')
                if found and found not in selected_hench:
                     selected_hench.append(found)

        # 3. FILL RANDOM
        if len(selected_hench) > total_hench_needed:
             selected_hench = selected_hench[:total_hench_needed]

        target_count_h = max(total_hench_needed, len(selected_hench))
        remaining_h = target_count_h - len(selected_hench)
        
        if remaining_h > 0:
            available = [
                h for h in self.data['henchmen'] 
                if h not in selected_hench
                and not any(b.lower() in (h.get('name') or h.get('group_name') or '').lower() for b in self.scheme_mods['banned_henchmen'])
            ]
            if len(available) >= remaining_h:
                selected_hench.extend(random.sample(available, remaining_h))
            else:
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
        
        # --- PRE-FILL PLAYER CHOICES ---
        if self.scheme_mods.get('player_picked_heroes', 0) > 0:
            for i in range(self.scheme_mods['player_picked_heroes']):
                deck.append({
                    "hero": f"CHOSEN BY PLAYER {i+1}",
                    "set": "Player Choice",
                    "team": "Any",
                    "is_placeholder": True
                })
       
        if not self.data.get('heroes'): raise Exception("No Heroes found.")
        available_heroes = [
            h for h in self.data['heroes'] 
            if h['hero'] not in self.scheme_mods['banned_heroes']
        ]
        
        # --- 0. MANUAL USER SELECTIONS (NEW) ---
        user_hero_picks = self.user_selections.get('heroes', [])
        for pick_name in user_hero_picks:
            # Use helper
            chosen = self._find_by_ui_name(pick_name, available_heroes, 'hero')
            if chosen:
                deck.append(chosen)
                available_heroes.remove(chosen)
        
        # --- HANDLE SPECIFIC HERO INCLUSIONS (Updated) ---
        for req in self.scheme_mods['required_hero_deck_includes']:
            req_name = req['name'].lower()
            search_terms = [t.strip() for t in req_name.split(' or ')]
            
            # Check if User Selections (already in deck) satisfy this
            already_have = 0
            for h in deck:
                if h.get('is_placeholder'): continue
                h_name = h['hero'].lower()
                if any(term in h_name for term in search_terms):
                    already_have += 1
            
            needed = max(0, req['count'] - already_have)
            
            if needed > 0:
                candidates = []
                for h in available_heroes:
                    h_name = h['hero'].lower()
                    if any(term in h_name for term in search_terms):
                        candidates.append(h)
                
                if len(candidates) >= needed:
                    chosen = random.sample(candidates, needed)
                    deck.extend(chosen)
                    for h in candidates:
                        if h in available_heroes: available_heroes.remove(h)
                else:
                    print(f"   [!] Warning: Not enough heroes matching '{req['name']}'.")
                    deck.extend(candidates)
                    for h in candidates:
                        if h in available_heroes: available_heroes.remove(h)

        # --- HANDLE REQUIRED TEAMS (Updated) ---
        for req in self.scheme_mods.get('required_teams', []):
            target_team = req['team'].lower()
            
            # Check User Selections
            already_have = 0
            for h in deck:
                if h.get('is_placeholder'): continue
                t = self._get_hero_team(h).lower()
                if target_team in t:
                    already_have += 1
            
            needed = max(0, req['count'] - already_have)
            
            if needed > 0:
                candidates = [h for h in available_heroes if target_team in self._get_hero_team(h).lower()]
                
                if len(candidates) >= needed:
                    chosen = random.sample(candidates, needed)
                    deck.extend(chosen)
                    for h in chosen:
                        if h in available_heroes: available_heroes.remove(h)
                else:
                    deck.extend(candidates)
                    for h in candidates:
                        if h in available_heroes: available_heroes.remove(h)

        # --- TEAM VERSUS SETUP ---
        if self.scheme_mods['team_versus_counts']:
            count_a, count_b = self.scheme_mods['team_versus_counts']
            teams = {}
            for h in available_heroes:
                t = self._get_hero_team(h)
                if t == 'Unknown': continue
                if t not in teams: teams[t] = []
                teams[t].append(h)
            
            valid_teams_a = [t for t, heroes in teams.items() if len(heroes) >= count_a]
            if len(valid_teams_a) >= 2:
                team_a_name = random.choice(valid_teams_a)
                heroes_a = random.sample(teams[team_a_name], count_a)
                valid_teams_b = [t for t in valid_teams_a if t != team_a_name and len(teams[t]) >= count_b]
                if valid_teams_b:
                    team_b_name = random.choice(valid_teams_b)
                    heroes_b = random.sample(teams[team_b_name], count_b)
                    deck = heroes_a + heroes_b
                    for h in deck: 
                        if h in available_heroes: available_heroes.remove(h)
                        
        # --- FILTER BANNED TEAMS ---
        if self.scheme_mods.get('banned_teams_from_open_selection'):
            available_heroes = [
                h for h in available_heroes 
                if self._get_hero_team(h).lower() not in self.scheme_mods['banned_teams_from_open_selection']
            ]
        
        # --- SMART MATCHING LOGIC ---
        target_count = self.scheme_mods['hero_deck_count']
        
        # --- NEW: Build Tag Context Report ---
        active_mechanics = []
        possible_mechanics = ["Mechanic_Wound", "Mechanic_Rescue", "Mechanic_Artifact", "Gen_KO", "Mechanic_Rise_Dead"]
        for m in possible_mechanics:
            if m in self.synergy_tags:
                active_mechanics.append(m)
        
        # NEW: Extract Enemy Counters (Triggers from Mastermind/Villains)
        active_counters = []
        setup_class_needs = set()
        setup_team_needs = set()
        
        for tag in self.synergy_tags:
            # Parse tags like "Class_Strength" or "Team_Avengers" from the enriched JSONs
            if tag.startswith("Class_"):
                cls = tag.split("_")[1].lower()
                setup_class_needs.add(cls)
                active_counters.append(f"Need {cls.title()}")
            elif tag.startswith("Team_"):
                # Tag format is "Team_XMen" -> need "xmen" for comparison
                tm = tag.split("_")[1].lower()
                setup_team_needs.add(tm)
                active_counters.append(f"Need {tm}")

        # Check Bystander override for Rescue logic
        if (self.scheme_mods.get('bystanders_override') or 0) > 5 and "Mechanic_Rescue" not in active_mechanics:
             active_mechanics.append("High Bystander Count (Rescue)")

        tag_report = {
            "Scheme": self._get_tags(self.setup['scheme']),
            "Mastermind": self._get_tags(self.setup['mastermind']),
            "Villains": {v.get('group_name') or v.get('name'): self._get_tags(v) for v in self.setup['villains']},
            "Henchmen": {h['name']: self._get_tags(h) for h in self.setup['henchmen']},
            "Active_Triggers": active_mechanics + active_counters
        }
        self.setup['synergy_overview'] = tag_report
        # -------------------------------------

        # Initialize log storage
        self.setup['synergy_logs'] = []

        def score_hero(hero):
            score = 0
            reasons = [] # Log reasons for debug
            
            # Combine text for scanning
            hero_text_blob = ""
            hero_costs = []
            for c in hero['cards']:
                abilities = " ".join(c.get('abilities', []))
                hero_text_blob += abilities.lower() + " "
                if c.get('cost'): 
                    val = int(re.search(r'\d+', str(c['cost'])).group(0)) if re.search(r'\d+', str(c['cost'])) else 0
                    hero_costs.append(val)
            
            # A. SETUP-TO-HERO CONFIGURABLE SYNERGIES
            hero_tags = self._get_hero_tags(hero)
            for rule in self.synergy_config.get('setup_to_hero_rules', []):
                trigger_tag = rule.get('trigger_tag')
                bystander_val = self.scheme_mods.get('bystanders_override') or 0
                is_high_bystanders = (trigger_tag == "Mechanic_Rescue" and bystander_val > 5)
                
                if trigger_tag in self.synergy_tags or is_high_bystanders:
                    # Check tags match
                    tag_matched = any(t in hero_tags for t in rule.get('matching_tags', []))
                    # Check text keywords match (case-insensitive)
                    keyword_matched = any(kw.lower() in hero_text_blob for kw in rule.get('keywords', []))
                    
                    if tag_matched or keyword_matched:
                        w = rule.get('weight', 0.0)
                        score += w
                        reasons.append(f"{rule.get('display_name')} (+{w})")

            # B. CURVE BALANCING
            current_deck_costs = []
            for h in deck:
                if h.get('is_placeholder'): continue
                for c in h.get('cards', []):
                     if c.get('cost'):
                        val = int(re.search(r'\d+', str(c['cost'])).group(0)) if re.search(r'\d+', str(c['cost'])) else 0
                        current_deck_costs.append(val)
            
            deck_avg = sum(current_deck_costs) / len(current_deck_costs) if current_deck_costs else 0
            cand_avg = sum(hero_costs) / len(hero_costs) if hero_costs else 0

            weights = self.synergy_config.get('weights', {})
            if not current_deck_costs:
                if 3.5 <= cand_avg <= 4.5:
                    w = weights.get('curve_balanced_starter', 2.0)
                    score += w
                    reasons.append(f"Balanced Starter (+{w})")
            else:
                if deck_avg > 4.2:
                    if cand_avg < 3.5: 
                        w = weights.get('curve_fixer_cheap', 4.0)
                        score += w
                        reasons.append(f"Curve Fixer (Cheap) (+{w})")
                    elif cand_avg > 4.5: 
                        w = weights.get('curve_penalty_expensive', -2.0)
                        score += w
                        reasons.append(f"Curve Penalty (Too Expensive) ({w})")
                elif deck_avg < 3.0:
                    if cand_avg > 4.0: 
                        w = weights.get('curve_fixer_heavy', 3.0)
                        score += w
                        reasons.append(f"Curve Fixer (Heavy) (+{w})")
                elif 3.0 <= cand_avg <= 4.0:
                    w = weights.get('curve_normal', 1.0)
                    score += w
                    reasons.append(f"Curve Maintainer (+{w})")

            # --- ENEMY COUNTERS (Mastermind/Villain Triggers) ---
            # 1. Class Counters
            hero_classes = set()
            for c in hero['cards']:
                for cls in c.get('classes', []):
                    hero_classes.add(cls.lower())
            
            matched_classes = hero_classes.intersection(setup_class_needs)
            if matched_classes:
                w = weights.get('enemy_counter_class', 3.0)
                score += w
                reasons.append(f"Enemy Counter: {', '.join(matched_classes).title()} (+{w})")

            # 2. Team Counters
            my_team = self._get_hero_team(hero)
            if my_team != 'Unknown':
                # Normalization to match the "Team_GuardiansOfTheGalaxy" -> "guardiansofthegalaxy" format
                clean_my_team = my_team.replace('-', ' ').title().replace(' ', '').lower()
                if clean_my_team in setup_team_needs:
                    w = weights.get('enemy_counter_team', 3.0)
                    score += w
                    reasons.append(f"Enemy Counter: {my_team} (+{w})")
            # ---------------------------------------------------------

            # C. CONDITIONAL TEAM SYNERGY
            current_teams = [self._get_hero_team(h) for h in deck if not h.get('is_placeholder')]
            my_team = self._get_hero_team(hero).lower()
            
            if my_team != 'unknown':
                team_trigger_pattern = f"[{my_team}]"
                requires_team_synergy = team_trigger_pattern in hero_text_blob
                
                if my_team in current_teams:
                    if requires_team_synergy:
                        w = weights.get('team_requirement_match', 4.0)
                        score += w
                        reasons.append(f"Team Requirement: {my_team.title()} (+{w})")
                    else:
                        w = weights.get('team_simple_match', 0.5)
                        score += w
                        reasons.append(f"Team Match: {my_team.title()} (+{w})")

            # D. CLASS SYNERGY (SMART BIDIRECTIONAL)
            # 1. Analyze Deck State
            deck_classes = set()
            deck_needs = set()
            standard_classes = ["strength", "instinct", "covert", "tech", "ranged"]
            
            for h in deck:
                if h.get('is_placeholder'): continue
                for c in h.get('cards', []):
                    # Gather provided classes
                    for cls in c.get('classes', []):
                        deck_classes.add(cls.lower())
                    # Gather required classes (Scan text for [class])
                    ab_text = " ".join(c.get('abilities', [])).lower()
                    for s_cls in standard_classes:
                        if f"[{s_cls}]" in ab_text:
                            deck_needs.add(s_cls)
            
            # 2. Analyze Candidate
            cand_classes = set()
            cand_needs = set()
            
            for c in hero['cards']:
                for cls in c.get('classes', []):
                    cand_classes.add(cls.lower())
            
            # Check Candidate Requirements (using the pre-generated blob)
            for s_cls in standard_classes:
                if f"[{s_cls}]" in hero_text_blob:
                    cand_needs.add(s_cls)
            
            # 3. Score
            # Case A: Candidate triggers Deck (Deck needs X, Candidate has X)
            triggers_deck = cand_classes.intersection(deck_needs)
            if triggers_deck:
                w = weights.get('class_trigger_deck', 3.0)
                score += w
                reasons.append(f"Satisfies Deck Requirement: {', '.join(triggers_deck).title()} (+{w})")

            # Case B: Deck triggers Candidate (Candidate needs Y, Deck has Y)
            triggered_by_deck = cand_needs.intersection(deck_classes)
            if triggered_by_deck:
                w = weights.get('class_triggered_by_deck', 3.0)
                score += w
                reasons.append(f"Triggered by Deck: {', '.join(triggered_by_deck).title()} (+{w})")

            # Case C: Simple Class Match (Stacking)
            # Only applied if no specific triggers are active, to maintain consistency
            if not triggers_deck and not triggered_by_deck:
                if not cand_classes.isdisjoint(deck_classes):
                    w = weights.get('class_simple_match', 1.0)
                    score += w
                    reasons.append(f"Class Match (+{w})")

            # E. HERO-TO-HERO CONFIGURABLE SYNERGIES
            for rule in self.synergy_config.get('hero_to_hero_rules', []):
                rule_type = rule.get('type')
                if rule_type == 'tag_cross_count':
                    synergy_tag = rule.get('synergy_tag')
                    target_tags = rule.get('target_tags', [])
                    
                    def has_target_tag(card):
                        # 1. Direct tag check
                        card_tags = []
                        if 'tags' in card:
                            for cat, tags in card['tags'].items(): card_tags.extend(tags)
                        if any(t in card_tags for t in target_tags):
                            return True
                        # 2. Fallback numeric cost check for Cost_X tags
                        if card.get('cost'):
                            try:
                                cost_val = int(re.search(r'\d+', str(card['cost'])).group(0))
                                cost_tag = f"Cost_{cost_val}"
                                if cost_tag in target_tags:
                                    return True
                            except:
                                pass
                        return False

                    # 1. Check if candidate has synergy tag
                    cand_has_synergy = synergy_tag in hero_tags
                    cand_target_count = sum(1 for c in hero['cards'] if has_target_tag(c))
                            
                    # 2. Check deck state
                    deck_has_synergy = False
                    deck_target_count = 0
                    for h in deck:
                        if h.get('is_placeholder'): continue
                        h_tags = self._get_hero_tags(h)
                        if synergy_tag in h_tags:
                            deck_has_synergy = True
                        deck_target_count += sum(1 for c in h.get('cards', []) if has_target_tag(c))
                                
                    # 3. Apply scores
                    if cand_has_synergy and deck_target_count > 0:
                        cand_to_deck_w = rule.get('candidate_to_deck_weight', 0.0)
                        bonus = deck_target_count * cand_to_deck_w
                        score += bonus
                        reasons.append(f"{rule.get('display_name')}: Triggered by {deck_target_count} target cards in deck (+{bonus})")
                        
                    if deck_has_synergy and cand_target_count > 0:
                        deck_to_cand_w = rule.get('deck_to_candidate_weight', 0.0)
                        bonus = cand_target_count * deck_to_cand_w
                        score += bonus
                        reasons.append(f"{rule.get('display_name')}: Candidate has {cand_target_count} target cards (+{bonus})")

                elif rule_type == 'tag_cross_match':
                    tag_a = rule.get('tag_a')
                    tag_b = rule.get('tag_b')
                    weight = rule.get('weight', 0.0)
                    
                    cand_tags = hero_tags
                    
                    deck_tags = set()
                    for h in deck:
                        if h.get('is_placeholder'): continue
                        deck_tags.update(self._get_hero_tags(h))
                        
                    has_match = (
                        (tag_a in cand_tags and tag_b in deck_tags) or
                        (tag_b in cand_tags and tag_a in deck_tags)
                    )
                    
                    if has_match:
                        score += weight
                        reasons.append(f"{rule.get('display_name')} (+{weight})")

            # Random Noise
            rng = random.uniform(0, 1.5)
            score += rng
            # Rounding for cleaner logs
            return score, reasons


# --- SEEDING: Pick 1 Random Hero (User Request) ---
        # We pick one hero completely at random first. 
        # The Smart Matching Logic will then build around this hero (and any required ones).
        if len(deck) < target_count and available_heroes:
            seed = random.choice(available_heroes)
            deck.append(seed)
            available_heroes.remove(seed)
            
            self.setup['synergy_logs'].append({
                "hero": seed['hero'],
                "score": 0,
                "reasons": ["Random Seed (Variety)"]
            })

        # --- SELECTION LOOP ---
        while len(deck) < target_count and available_heroes:
            sample_size = min(10, len(available_heroes))
            candidates = random.sample(available_heroes, sample_size)
            
            best_candidate = None
            best_score = -999
            best_reasons = []
            
            for h in candidates:
                s, r = score_hero(h)
                if s > best_score:
                    best_score = s
                    best_candidate = h
                    best_reasons = r
            
            deck.append(best_candidate)
            available_heroes.remove(best_candidate)
            
            # Save Log
            self.setup['synergy_logs'].append({
                "hero": best_candidate['hero'],
                "score": round(best_score, 2),
                "reasons": best_reasons
            })
            
        self.setup['heroes'] = deck
        
        # --- Pick separate heroes for the Villain Deck ---
        self.setup['villain_deck_heroes'] = []
        
        # 1. Specific
        for req_name in self.scheme_mods['required_villain_deck_heroes']:
            found = self._find_hero_by_name(req_name)
            if found:
                self.setup['villain_deck_heroes'].append(found)
                if found in available_heroes: available_heroes.remove(found)
            else:
                if available_heroes:
                    fallback = random.choice(available_heroes)
                    self.setup['villain_deck_heroes'].append(fallback)
                    available_heroes.remove(fallback)

        # 2. Generic Extras
        filled_count = len(self.setup['villain_deck_heroes'])
        needed_count = self.scheme_mods['villain_deck_heroes']
        remaining = needed_count - filled_count
        
        if remaining > 0:
            if len(available_heroes) >= remaining:
                extras = random.sample(available_heroes, remaining)
                self.setup['villain_deck_heroes'].extend(extras)

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
                
       # Determine suffixes for Half-Deck mechanic
        v_suffix = ""
        h_suffix = ""
        if self.scheme_mods['half_deck_mechanic']:
            v_suffix = " (Use 4 random cards)"
            # Handle 1-player specific rule (2 Henchmen) vs standard half (5 Henchmen)
            if self.player_count == 1:
                h_suffix = " (Use 2 random cards)" 
            else:
                h_suffix = " (Use 5 random cards)"

        # Helper to format Henchmen list with Alias AND Suffix
        final_henchmen_list = []
        for i, h in enumerate(self.setup['henchmen']):
            display_name = f"{h['name']} ({h['set']})"
            
            # Apply alias to the LAST group if defined
            if self.scheme_mods['henchman_alias'] and i == len(self.setup['henchmen']) - 1:
                display_name = f"{display_name} (as {self.scheme_mods['henchman_alias']})"
            
            # Apply Half-Deck Suffix
            display_name += h_suffix
            
            final_henchmen_list.append(display_name)
            
        vd_heroes_formatted = []

        result = {
            "raw_mastermind": self.setup['mastermind'],
            "raw_scheme": self.setup['scheme'],
            "raw_heroes": self.setup['heroes'],
            "raw_villains": self.setup['villains'],
            "raw_henchmen": self.setup['henchmen'],
            "Mastermind": f"{self.setup['mastermind']['name']} ({self.setup['mastermind']['set']})",
            # We now pass the raw list for better UI handling
            "Lurking_Masterminds": [f"{m['name']} ({m['set']})" for m in self.setup.get('lurking_masterminds', [])],
            "Scheme": f"{self.setup['scheme']['name']} ({self.setup['scheme']['set']})",
            "Scheme_Description": self.setup['special_rules'],
            "Villains": [f"{v['group_name']} ({v['set']}){v_suffix}" for v in self.setup['villains']],
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
            "synergy_logs": self.setup.get('synergy_logs', []),
            "synergy_overview": self.setup.get('synergy_overview', {}),
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

def get_team_badge(team_name):
    if not team_name:
        return ("👥", "No Team", "#bdc3c7")
    team_map = {
        "avengers": ("🅰️", "Avengers", "#e74c3c"),
        "x-men": ("❌", "X-Men", "#f1c40f"),
        "spider-friends": ("🕷️", "Spider-Friends", "#3498db"),
        "shield": ("🛡️", "S.H.I.E.L.D.", "#7f8c8d"),
        "guardians-of-the-galaxy": ("🌌", "Guardians", "#9b59b6"),
        "fantastic-four": ("4️⃣", "Fantastic Four", "#2980b9"),
        "marvel-knights": ("🌙", "Marvel Knights", "#1abc9c"),
        "x-force": ("❌", "X-Force", "#2c3e50"),
        "cabal": ("💀", "Cabal", "#95a5a6"),
        "sinister-six": ("🐙", "Sinister Six", "#27ae60"),
        "illuminati": ("👁️", "Illuminati", "#f39c12"),
        "foes-of-asgard": ("⚡", "Foes of Asgard", "#d35400")
    }
    t_lower = str(team_name).lower().strip()
    if t_lower in team_map:
        return team_map[t_lower]
    return ("👥", str(team_name).title(), "#bdc3c7")

def get_class_badge(class_name):
    if not class_name:
        return ("▫️", "No Class", "#bdc3c7")
    class_map = {
        "strength": ("💪", "Strength", "#e67e22"),
        "instinct": ("🐾", "Instinct", "#2ecc71"),
        "covert": ("🕵️", "Covert", "#e74c3c"),
        "tech": ("🛠️", "Tech", "#3498db"),
        "ranged": ("🏹", "Ranged", "#9b59b6")
    }
    c_lower = str(class_name).lower().strip()
    if c_lower in class_map:
        return class_map[c_lower]
    return ("▫️", str(class_name).title(), "#bdc3c7")

def inject_custom_styles():
    st.markdown("""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
            
            /* Global fonts override - keep safe from icon fonts */
            html, body, p, h1, h2, h3, h4, h5, h6, label, select, button, input {
                font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
            }
            
            /* Header custom styling */
            h1, h2, h3 {
                font-family: 'Outfit', sans-serif !important;
                font-weight: 800 !important;
                letter-spacing: -0.5px;
            }
            
            /* Glassmorphic cards */
            .premium-card {
                background: rgba(31, 40, 51, 0.45);
                backdrop-filter: blur(10px);
                -webkit-backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
                transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
            }
            
            .premium-card:hover {
                transform: translateY(-4px);
                border-color: rgba(122, 34, 255, 0.4);
                box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5), 0 0 15px rgba(122, 34, 255, 0.15);
            }
            
            /* Grid and sub-element alignment */
            .card-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 12px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding-bottom: 8px;
            }
            
            .card-title {
                font-size: 1.15rem;
                font-weight: 800;
                color: #FFFFFF;
                margin: 0;
            }
            
            .card-subtitle {
                font-size: 0.8rem;
                color: rgba(255, 255, 255, 0.45);
                margin: 4px 0 12px 0;
            }
            
            /* Styled badges */
            .badge-pill {
                display: inline-flex;
                align-items: center;
                padding: 4px 10px;
                border-radius: 50px;
                font-size: 0.72rem;
                font-weight: 600;
                margin: 2px 4px 2px 0;
                line-height: 1;
                border: 1px solid transparent;
            }
            
            /* Scrollbar adjustments */
            ::-webkit-scrollbar {
                width: 8px;
                height: 8px;
            }
            ::-webkit-scrollbar-track {
                background: rgba(11, 12, 16, 0.5);
            }
            ::-webkit-scrollbar-thumb {
                background: rgba(122, 34, 255, 0.3);
                border-radius: 4px;
            }
            ::-webkit-scrollbar-thumb:hover {
                background: rgba(122, 34, 255, 0.6);
            }
            
            /* Dials & Stats */
            .metric-widget {
                background: rgba(31, 40, 51, 0.3);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.05);
                padding: 15px;
                text-align: center;
                box-shadow: 0 4px 15px rgba(0,0,0,0.15);
            }
            
            .metric-label {
                font-size: 0.75rem;
                color: rgba(255, 255, 255, 0.5);
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 5px;
            }
            
            .metric-val {
                font-size: 1.8rem;
                font-weight: 800;
                color: #7A22FF;
                text-shadow: 0 0 10px rgba(122, 34, 255, 0.4);
            }
            
            /* Custom styled lists */
            .styled-list {
                list-style-type: none;
                padding-left: 0;
                margin: 0;
            }
            .styled-list li {
                padding: 6px 0;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                color: rgba(255, 255, 255, 0.85);
                font-size: 0.92rem;
            }
            .styled-list li:last-child {
                border-bottom: none;
            }
            
            /* Custom Primary Button Glow */
            div.stButton > button:first-child {
                background: linear-gradient(135deg, #7A22FF 0%, #5400D1 100%) !important;
                border: none !important;
                color: white !important;
                font-weight: 800 !important;
                padding: 10px 24px !important;
                border-radius: 12px !important;
                box-shadow: 0 4px 20px rgba(122, 34, 255, 0.3) !important;
                transition: all 0.3s ease !important;
            }
            div.stButton > button:first-child:hover {
                box-shadow: 0 6px 25px rgba(122, 34, 255, 0.6) !important;
                transform: translateY(-2px) !important;
            }
        </style>
    """, unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="Legendary Randomizer", page_icon="🦸", layout="wide")
    inject_custom_styles()

    # --- PENDING COPY SETUP LOGIC ---
    if 'pending_copy_setup' in st.session_state:
        setup_data, p_val, s_val = st.session_state.pop('pending_copy_setup')
        st.session_state['player_count'] = p_val
        st.session_state['selected_expansions'] = s_val
        st.session_state['apply_copy_setup'] = setup_data
        st.rerun()

    # --- Sidebar: Configuration ---
    st.sidebar.header("⚙️ Setup")
    
    # 1. Player Count
    players = st.sidebar.slider("Number of Players", min_value=1, max_value=5, value=3, key="player_count")
    
    # --- LOAD RAW DATA & SETS ---
    raw_data = {}
    all_sets = set()
    
    try:
        files = {
            "schemes": "enriched_schemes.json",
            "masterminds": "enriched_masterminds.json",
            "villains": "enriched_villains.json",
            "henchmen": "enriched_henchmen.json",
            "heroes": "enriched_heroes.json"
        }
        for key, filename in files.items():
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    raw_data[key] = data
                    for item in data:
                        if item.get("set"):
                            for s in item["set"].split('/'):
                                all_sets.add(s.strip())
    except Exception as e:
        st.error(f"Error loading data: {e}")

    sorted_sets = sorted(list(all_sets))

    # 2. Set Selection
    st.sidebar.subheader("📚 Expansions")
    select_all = st.sidebar.checkbox("Select All Expansions", value=False)
    
    if select_all:
        selected_sets = sorted_sets
        st.sidebar.success(f"All {len(sorted_sets)} expansions selected.")
    else:
        desired_defaults = ["Core Set", "Marvel Studios' What If...?"]
        defaults = [s for s in desired_defaults if s in sorted_sets]
        if not defaults and sorted_sets: defaults = [sorted_sets[0]]
        selected_sets = st.sidebar.multiselect("Select Expansions", sorted_sets, default=defaults, key="selected_expansions")

    if not selected_sets:
        st.warning("Please select at least one expansion.")
        return

    # --- FILTER DATA BASED ON SELECTION ---
    selected_sets_lower = {s.lower() for s in selected_sets}
    def is_in_selection(item):
        item_set = item.get('set', '')
        if not item_set: return False
        parts = [p.strip().lower() for p in item_set.split('/')]
        return any(p in selected_sets_lower for p in parts)

    filtered_data = {}
    filtered_options = {}
    
    for key, items in raw_data.items():
        # 1. Filter items belonging to selected sets
        valid_items = [i for i in items if is_in_selection(i)]
        filtered_data[key] = valid_items
        
        # 2. Extract names with Set Disambiguation logic
        # Count occurrences of each name
        name_counts = {}
        for item in valid_items:
            if key == "heroes": n = item['hero']
            elif key == "villains": n = item.get('group_name') or item.get('name')
            else: n = item.get('name')
            name_counts[n] = name_counts.get(n, 0) + 1
            
        final_names = []
        for item in valid_items:
            if key == "heroes": n = item['hero']
            elif key == "villains": n = item.get('group_name') or item.get('name')
            else: n = item.get('name')
            
            # If duplicates exist across sets, append (Set Name)
            if name_counts[n] > 1:
                final_names.append(f"{n} ({item.get('set', 'Unknown')})")
            else:
                final_names.append(n)
        
        filtered_options[key] = ["Random"] + sorted(list(set(final_names)))

    # Apply copy setup logic if present in session state
    if 'apply_copy_setup' in st.session_state:
        setup_data = st.session_state.pop('apply_copy_setup')
        
        def find_sidebar_option(name, options):
            if not name or not options:
                return "Random"
            if name in options:
                return name
            name_lower = name.lower()
            for opt in options:
                if opt.lower() == name_lower:
                    return opt
                if opt.lower().startswith(name_lower + " ("):
                    return opt
            clean_name = re.sub(r"\s*\(.*\)\s*$", "", name).strip().lower()
            for opt in options:
                opt_clean = re.sub(r"\s*\(.*\)\s*$", "", opt).strip().lower()
                if opt_clean == clean_name:
                    return opt
            return "Random"

        # 1. Scheme
        sch = setup_data['raw_scheme']['name']
        st.session_state['override_scheme'] = find_sidebar_option(sch, filtered_options.get('schemes', []))
        
        # 2. Mastermind
        mm = setup_data['raw_mastermind']['name']
        st.session_state['override_mastermind'] = find_sidebar_option(mm, filtered_options.get('masterminds', []))
        
        # 3. Villains
        for i, v in enumerate(setup_data.get('Villains', [])):
            matched = find_sidebar_option(v, filtered_options.get('villains', []))
            st.session_state[f"v_{i}"] = matched
            
        # 4. Henchmen
        for i, h in enumerate(setup_data.get('Henchmen', [])):
            matched = find_sidebar_option(h, filtered_options.get('henchmen', []))
            st.session_state[f"h_{i}"] = matched
            
        # 5. Heroes
        for i, h_obj in enumerate(setup_data.get('raw_heroes', [])):
            matched = find_sidebar_option(h_obj.get('hero', ''), filtered_options.get('heroes', []))
            st.session_state[f"hero_{i}"] = matched

    st.sidebar.divider()
    st.sidebar.subheader("🔒 Manual Overrides")

    if st.sidebar.button("🔄 Reset Overrides to Random", use_container_width=True):
        st.session_state['override_scheme'] = "Random"
        st.session_state['override_mastermind'] = "Random"
        for key in list(st.session_state.keys()):
            if key.startswith("v_") or key.startswith("h_") or key.startswith("hero_"):
                st.session_state[key] = "Random"
        st.rerun()

    # 3. Manual Selections
    user_selections = {}
    
    # Helper: Find option match
    def find_option_match(target, options):
        if not target or target == "Unknown": return None
        if target in options: return target
        target_lower = target.lower()
        for opt in options:
            if opt.lower() == target_lower: return opt
        for opt in options:
            if opt == "Random": continue
            if target_lower in opt.lower() or opt.lower() in target_lower:
                return opt
        return None

    # UI: Scheme & Mastermind
    user_selections['scheme'] = st.sidebar.selectbox("Scheme", filtered_options.get('schemes', ["Random"]), key="override_scheme")
    user_selections['mastermind'] = st.sidebar.selectbox("Mastermind", filtered_options.get('masterminds', ["Random"]), key="override_mastermind")
    
    # --- PRE-ANALYSIS: CALCULATE DYNAMIC COUNTS & REQUIREMENTS ---
    # We create a temporary Randomizer to parse the rules of the selected Scheme
    
    # Defaults
    base_rules = SETUP_RULES[players]
    num_villains = base_rules['villains']
    num_henchmen = base_rules['henchmen']
    num_heroes = base_rules['heroes']
    
    locked_villains = []
    locked_henchmen = []

    if user_selections['scheme'] != "Random":
        # 1. Find Scheme Object
        scheme_obj = next((s for s in filtered_data['schemes'] if s['name'] == user_selections['scheme']), None)
        
        if scheme_obj:
            # 2. Run Parser (Dry Run)
            temp_r = LegendaryRandomizer(selected_sets, players)
            temp_r.data = filtered_data # Inject filtered data directly
            temp_r.parse_scheme_rules(scheme_obj)
            
            # 3. Apply Villain/Henchmen Counts
            # (Logic copied from pick_villains_and_henchmen)
            v_needed = base_rules['villains'] + temp_r.scheme_mods['extra_villains']
            h_needed = base_rules['henchmen'] + temp_r.scheme_mods['extra_henchmen']
            
            if temp_r.scheme_mods['double_group_count']:
                v_needed *= 2
                h_needed *= 2
                
            num_villains = v_needed
            num_henchmen = h_needed
            
            # 4. Apply Hero Count
            num_heroes = temp_r.scheme_mods['hero_deck_count']
            
            # 5. Extract Required Groups (Scheme)
            v_opts = filtered_options.get('villains', [])
            h_opts = filtered_options.get('henchmen', [])
            
            for req in temp_r.scheme_mods['required_villains']:
                m = find_option_match(req, v_opts)
                if m: locked_villains.append(m)
                
            for req in temp_r.scheme_mods['required_henchmen']:
                m = find_option_match(req, h_opts)
                if m: locked_henchmen.append(m)

    # --- MASTERMIND LEAD LOCKING ---
    if user_selections['mastermind'] != "Random":
        mm_obj = next((m for m in filtered_data['masterminds'] if m['name'] == user_selections['mastermind']), None)
        if mm_obj:
            lead = mm_obj.get('always_leads')
            if lead:
                v_opts = filtered_options.get('villains', [])
                match_v = find_option_match(lead, v_opts)
                if match_v and match_v not in locked_villains:
                    locked_villains.append(match_v)
                
                h_opts = filtered_options.get('henchmen', [])
                match_h = find_option_match(lead, h_opts)
                if match_h and match_h not in locked_henchmen:
                    locked_henchmen.append(match_h)

    # --- GATHER HERO CONSTRAINTS ---
    # We map abstract requirements (Team/Name) to specific slots
    hero_constraints = []
    
    # 1. Specific Includes (e.g. "Name contains Hulk")
    # We retrieve these from the temp_randomizer if it ran
    if user_selections['scheme'] != "Random" and 'temp_r' in locals():
        for req in temp_r.scheme_mods['required_hero_deck_includes']:
            count = req.get('count', 1)
            for _ in range(count):
                hero_constraints.append({'type': 'name', 'val': req['name']})
                
        for req in temp_r.scheme_mods['required_teams']:
            count = req.get('count', 1)
            for _ in range(count):
                hero_constraints.append({'type': 'team', 'val': req['team']})
    # --- RENDER DYNAMIC SIDEBAR ---

    # Villains
    st.sidebar.markdown(f"**Villains ({num_villains} Groups)**")
    user_selections['villains'] = []
    
    # Track used names to remove from subsequent dropdowns
    # Initialize with locked items to ensure they aren't manually picked in earlier open slots if order varies
    used_villains = {v for v in locked_villains if v}

    for i in range(num_villains):
        v_base_opts = filtered_options.get('villains', ["Random"])
        
        # Identify if this specific slot is locked
        current_lock = locked_villains[i] if i < len(locked_villains) else None
        
        # Filter Options: Allow "Random", the specific lock for THIS slot, or anything not yet used
        v_opts = [
            opt for opt in v_base_opts 
            if opt == "Random" or opt == current_lock or opt not in used_villains
        ]
        
        key = f"v_{i}"
        slot_index = 0
        slot_disabled = False
        
        if current_lock:
            if current_lock in v_opts:
                slot_index = v_opts.index(current_lock)
                slot_disabled = True
                st.session_state[key] = current_lock # Force update
        
        v_pick = st.sidebar.selectbox(f"Villain Group {i+1}", v_opts, index=slot_index, disabled=slot_disabled, key=key)
        
        if v_pick != "Random": 
            user_selections['villains'].append(v_pick)
            # Add to used list so next dropdowns don't show it
            used_villains.add(v_pick)

    # Henchmen
    st.sidebar.markdown(f"**Henchmen ({num_henchmen} Groups)**")
    user_selections['henchmen'] = []
    used_henchmen = {h for h in locked_henchmen if h}

    for i in range(num_henchmen):
        h_base_opts = filtered_options.get('henchmen', ["Random"])
        current_lock = locked_henchmen[i] if i < len(locked_henchmen) else None
        
        h_opts = [
            opt for opt in h_base_opts 
            if opt == "Random" or opt == current_lock or opt not in used_henchmen
        ]
        
        key = f"h_{i}"
        slot_index = 0
        slot_disabled = False
        
        if current_lock:
            if current_lock in h_opts:
                slot_index = h_opts.index(current_lock)
                slot_disabled = True
                st.session_state[key] = current_lock
                
        h_pick = st.sidebar.selectbox(f"Henchman Group {i+1}", h_opts, index=slot_index, disabled=slot_disabled, key=key)
        
        if h_pick != "Random": 
            user_selections['henchmen'].append(h_pick)
            used_henchmen.add(h_pick)

    # Heroes
    st.sidebar.markdown(f"**Heroes ({num_heroes} Heroes)**")
    user_selections['heroes'] = []
    used_heroes = set()

    # Create a lookup for hero data to check teams/names efficiently
    hero_lookup = {h['hero']: h for h in filtered_data['heroes']}

    for i in range(num_heroes):
        hero_base_opts = filtered_options.get('heroes', ["Random"])
        
        # Check for constraints on this slot
        constraint = hero_constraints[i] if i < len(hero_constraints) else None
        
        label = f"Hero {i+1}"
        filtered_opts = []
        
        if constraint:
            if constraint['type'] == 'team':
                req_team = constraint['val'].lower()
                label += f" ({req_team.title()} Required)"
                # Filter: Include Random + Heroes with matching team
                for opt in hero_base_opts:
                    if opt == "Random":
                        filtered_opts.append(opt)
                        continue
                    
                    h_obj = hero_lookup.get(opt)
                    if h_obj:
                        # Helper to find team (using same logic as class)
                        h_team = "Unknown"
                        if h_obj.get('cards'): h_team = h_obj['cards'][0].get('team', 'Unknown')
                        
                        if req_team in h_team.lower():
                            filtered_opts.append(opt)
                            
            elif constraint['type'] == 'name':
                req_name_frag = constraint['val'].lower()
                label += f" (Name: '{constraint['val']}')"
                # Filter: Include Random + Heroes matching name fragment
                for opt in hero_base_opts:
                    if opt == "Random":
                        filtered_opts.append(opt)
                        continue
                    
                    # Split fragment by " or " logic if present
                    fragments = [f.strip() for f in req_name_frag.split(' or ')]
                    if any(f in opt.lower() for f in fragments):
                        filtered_opts.append(opt)
        else:
            # No constraint -> All options
            filtered_opts = hero_base_opts

        # Final Filter: Remove used heroes (unless it's the constraint satisfied by Random)
        final_opts = [
            opt for opt in filtered_opts 
            if opt == "Random" or opt not in used_heroes
        ]
        
        # If filtering left us with nothing (e.g. no Avengers in selected sets), fallback
        if not final_opts: final_opts = ["Random"]

        hero_pick = st.sidebar.selectbox(label, final_opts, key=f"hero_{i}")
        
        if hero_pick != "Random": 
            user_selections['heroes'].append(hero_pick)
            used_heroes.add(hero_pick)

    # --- Main Area ---
    st.title("🦸 Legendary Setup Randomizer")
    
    tab_gen, tab_hist = st.tabs(["🎲 Generator", "📜 History & Stats"])
    
    with tab_gen:
        if st.session_state.get('current_setup'):
            col_gen1, col_gen2 = st.columns([2, 1])
            with col_gen1:
                if st.button("🎲 Generate New Setup", type="primary", use_container_width=True):
                    setup = run_randomizer(selected_sets, players, user_selections)
                    if setup:
                        st.session_state['current_setup'] = setup
                        add_to_history(setup, players, selected_sets)
                        st.rerun()
            with col_gen2:
                if st.button("📋 Copy Setup to Sidebar", use_container_width=True):
                    st.session_state['pending_copy_setup'] = (
                        st.session_state['current_setup'],
                        st.session_state.get('player_count', players),
                        st.session_state.get('selected_expansions', selected_sets)
                    )
                    st.success("Config copied! Adjust choices in the sidebar.")
                    st.rerun()
        else:
            if st.button("🎲 Generate New Setup", type="primary", use_container_width=True):
                setup = run_randomizer(selected_sets, players, user_selections)
                if setup:
                    st.session_state['current_setup'] = setup
                    add_to_history(setup, players, selected_sets)
                    st.rerun()
                
        if st.session_state.get('current_setup'):
            display_results(st.session_state['current_setup'])
        else:
            st.info("No active setup. Click the button above to generate a new scenario!")
            
    with tab_hist:
        st.subheader("📜 Generated Setups History")
        history = load_history()
        if not history:
            st.info("No setups in history yet. Generate some scenarios to track them here!")
        else:
            col_clear1, col_clear2 = st.columns([3, 1])
            with col_clear2:
                if st.button("🚨 Clear All History", type="secondary", use_container_width=True):
                    save_history([])
                    if 'current_setup' in st.session_state:
                        del st.session_state['current_setup']
                    st.success("History cleared!")
                    st.rerun()
            
            for idx, entry in enumerate(history):
                timestamp = entry.get('timestamp', '')
                try:
                    dt = datetime.datetime.fromisoformat(timestamp)
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    formatted_time = timestamp
                    
                setup_data = entry['setup']
                mm_name = setup_data['raw_mastermind']['name']
                sch_name = setup_data['raw_scheme']['name']
                hist_players = entry.get('players', 3)
                
                with st.expander(f"📅 {formatted_time} | 👥 {hist_players}P | 🦹 {mm_name} vs. 📜 {sch_name}"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**🦹 Mastermind:** {mm_name} *({setup_data['raw_mastermind']['set']})*")
                        st.markdown(f"**📜 Scheme:** {sch_name} *({setup_data['raw_scheme']['set']})*")
                        st.markdown(f"**😈 Villains:** {', '.join(setup_data['Villains'])}")
                        st.markdown(f"**🤖 Henchmen:** {', '.join(setup_data['Henchmen'])}")
                    with c2:
                        st.markdown("**🦸 Heroes:**")
                        for h in setup_data['Heroes']:
                            st.markdown(f"- {h}")
                            
                    st.divider()
                    col_btn1, col_btn2, col_btn3 = st.columns(3)
                    with col_btn1:
                        if st.button("🔄 Load into Generator", key=f"load_{entry['id']}_{idx}", use_container_width=True):
                            st.session_state['current_setup'] = setup_data
                            st.success("Setup loaded! Switch to the 🎲 Generator tab to view it.")
                            st.rerun()
                    with col_btn2:
                        if st.button("📋 Copy to Sidebar", key=f"copy_sb_{entry['id']}_{idx}", use_container_width=True):
                            st.session_state['pending_copy_setup'] = (
                                setup_data,
                                entry.get('players', 3),
                                entry.get('selected_sets', selected_sets)
                            )
                            st.success("Config copied to sidebar!")
                            st.rerun()
                    with col_btn3:
                        if st.button("🗑️ Delete from History", key=f"del_{entry['id']}_{idx}", use_container_width=True):
                            delete_from_history(entry['id'])
                            if st.session_state.get('current_setup') == setup_data:
                                del st.session_state['current_setup']
                            st.success("Deleted!")
                            st.rerun()

def run_randomizer(selected_sets, players, user_selections):
    with st.spinner('Consulting the Multiverse...'):
        try:
            # Pass user_selections to the class
            randomizer = LegendaryRandomizer(selected_sets, players, user_selections)
            setup = randomizer.generate_setup()
            
            if setup:
                return setup
            else:
                st.error("Failed to generate setup. Check your data files.")
        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.code(traceback.format_exc())
    return None

def display_results(setup):
    def clean_html(html_str):
        return "".join(line.strip() for line in html_str.split("\n"))

    # Helper to build hero card HTML
    def get_hero_card_html(h):
        hero_name = h.get('hero')
        hero_set = h.get('set', 'Unknown')
        is_placeholder = h.get('is_placeholder', False)
        
        if is_placeholder:
            return clean_html(f"""
            <div class='premium-card' style='height: 100%; display: flex; flex-direction: column; justify-content: space-between;'>
                <div>
                    <div class='card-header'>
                        <span class='badge-pill' style='background: rgba(255, 255, 255, 0.03); border: 1px solid #bdc3c7; color: #bdc3c7;'>👥 Player Choice</span>
                    </div>
                    <div class='card-title'>{hero_name}</div>
                </div>
            </div>
            """)
        
        team_name = 'Unknown'
        if h.get('cards') and len(h['cards']) > 0:
            team_name = h['cards'][0].get('team', 'Unknown')
            
        team_icon, team_title, team_color = get_team_badge(team_name)
        
        classes = set()
        for card in h.get('cards', []):
            for cls in card.get('classes', []):
                classes.add(cls)
                
        class_badges_html = ""
        for cls in sorted(list(classes)):
            cls_icon, cls_title, cls_color = get_class_badge(cls)
            class_badges_html += f"""
            <span class='badge-pill' style='background: rgba(255, 255, 255, 0.03); border: 1px solid {cls_color}; color: {cls_color};'>{cls_icon} {cls_title}</span>
            """
            
        return clean_html(f"""
        <div class='premium-card' style='height: 100%; display: flex; flex-direction: column; justify-content: space-between;'>
            <div>
                <div class='card-header'>
                    <span class='badge-pill' style='background: rgba(255, 255, 255, 0.03); border: 1px solid {team_color}; color: {team_color};'>{team_icon} {team_title}</span>
                    <span style='font-size: 0.75rem; color: rgba(255, 255, 255, 0.45);'>📚 {hero_set}</span>
                </div>
                <div class='card-title'>{hero_name}</div>
            </div>
            <div style='margin-top: 15px;'>
                <div style='font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.5px; color: rgba(255,255,255,0.4); margin-bottom: 5px;'>Classes</div>
                {class_badges_html}
            </div>
        </div>
        """)

    # --- 1. Mastermind & Scheme ---
    col1, col2 = st.columns(2)
    with col1:
        mm_name = setup['raw_mastermind']['name']
        mm_set = setup['raw_mastermind']['set']
        leads = setup['raw_mastermind'].get('always_leads')
        leads_html = f"<div class='card-subtitle'>Always Leads: {leads}</div>" if leads else ""
        
        mm_html = clean_html(f"""
        <div class='premium-card'>
            <div class='card-header'>
                <span class='badge-pill' style='background: rgba(255, 255, 255, 0.03); border: 1px solid #7A22FF; color: #7A22FF;'>🦹 Mastermind</span>
                <span style='font-size: 0.8rem; color: rgba(255, 255, 255, 0.5);'>📚 {mm_set}</span>
            </div>
            <div class='card-title'>{mm_name}</div>
            {leads_html}
        """)
        if setup.get('Lurking_Masterminds'):
            mm_html += "<div style='margin-top: 12px; font-weight: 600; font-size: 0.85rem; color: rgba(255,255,255,0.7);'>👥 Lurking Masterminds:</div>"
            for lm in setup['Lurking_Masterminds']:
                mm_html += f"<div style='font-size: 0.8rem; color: rgba(255,255,255,0.6);'>- {lm}</div>"
        if setup.get('Tyrant_Masterminds'):
            mm_html += "<div style='margin-top: 12px; font-weight: 600; font-size: 0.85rem; color: rgba(255,255,255,0.7);'>👑 Tyrant Masterminds:</div>"
            for tm in setup['Tyrant_Masterminds']:
                mm_html += f"<div style='font-size: 0.8rem; color: rgba(255,255,255,0.6);'>- {tm}</div>"
        if setup.get('Drained_Mastermind'):
            dm = setup['Drained_Mastermind']
            mm_html += clean_html(f"""
            <div style='margin-top: 12px; font-weight: 600; font-size: 0.85rem; color: rgba(255,255,255,0.7);'>🔻 Drained Mastermind:</div>
            <div style='font-size: 0.8rem; color: rgba(255,255,255,0.6);'>{dm['name']} ({dm['set']}) <i>(Set aside)</i></div>
            """)
        mm_html += "</div>"
        st.markdown(mm_html, unsafe_allow_html=True)

    with col2:
        sch_name = setup['raw_scheme']['name']
        sch_set = setup['raw_scheme']['set']
        
        sch_html = clean_html(f"""
        <div class='premium-card'>
            <div class='card-header'>
                <span class='badge-pill' style='background: rgba(255, 255, 255, 0.03); border: 1px solid #f39c12; color: #f39c12;'>📜 Scheme</span>
                <span style='font-size: 0.8rem; color: rgba(255, 255, 255, 0.5);'>📚 {sch_set}</span>
            </div>
            <div class='card-title'>{sch_name}</div>
        """)
        if setup.get('Custom_Deck'):
            cd = setup['Custom_Deck']
            sch_html += "<div style='margin-top: 12px; font-weight: 600; font-size: 0.85rem; color: #e74c3c;'>📦 " + cd['name'] + " Content:</div>"
            for line in cd['lines']:
                sch_html += f"<div style='font-size: 0.8rem; color: #e74c3c;'>- {line}</div>"
        sch_html += "</div>"
        st.markdown(sch_html, unsafe_allow_html=True)

    # --- NEW DEBUG SECTION ---
    if SHOW_SYNERGY_DEBUG and setup.get('synergy_logs'):
        st.divider()
        with st.expander("🔍 Synergy Debug Report", expanded=False):
            ov = setup.get('synergy_overview', {})
            if ov:
                st.markdown("### 🏷️ Active Tags & Triggers")
                st.write("**Looking for Mechanics:**", ", ".join(ov['Active_Triggers']) if ov['Active_Triggers'] else "None (Pure Stat Balancing)")
                
                c1, c2 = st.columns(2)
                with c1:
                    st.caption(f"**Scheme Tags:** {ov['Scheme']}")
                    st.caption(f"**Mastermind Tags:** {ov['Mastermind']}")
                with c2:
                    st.caption("**Villain Tags:**")
                    for k,v in ov['Villains'].items():
                        if v: st.caption(f"- {k}: {v}")
                    st.caption("**Henchmen Tags:**")
                    for k,v in ov['Henchmen'].items():
                        if v: st.caption(f"- {k}: {v}")
                st.divider()
        
            st.info("This section shows why specific heroes were selected.")
            
            for log in setup['synergy_logs']:
                st.markdown(f"**{log['hero']}** (Score: {log['score']})")
                if log['reasons']:
                    for r in log['reasons']:
                        st.caption(f"• {r}")
                else:
                    st.caption("• Random Selection / Low Synergy")
                st.divider()

    # --- 2. Villains & Henchmen ---
    col3, col4 = st.columns(2)
    with col3:
        villains_html = clean_html("""
        <div class='premium-card'>
            <div class='card-header'>
                <span class='badge-pill' style='background: rgba(255, 255, 255, 0.03); border: 1px solid #e74c3c; color: #e74c3c;'>😈 Villains</span>
            </div>
            <ul class='styled-list'>
        """)
        for v in setup['Villains']:
            villains_html += f"<li>{v}</li>"
        villains_html += "</ul></div>"
        st.markdown(villains_html, unsafe_allow_html=True)
            
    with col4:
        henchmen_html = clean_html("""
        <div class='premium-card'>
            <div class='card-header'>
                <span class='badge-pill' style='background: rgba(255, 255, 255, 0.03); border: 1px solid #2ecc71; color: #2ecc71;'>🤖 Henchmen</span>
            </div>
            <ul class='styled-list'>
        """)
        for h in setup['Henchmen']:
            henchmen_html += f"<li>{h}</li>"
        henchmen_html += "</ul></div>"
        st.markdown(henchmen_html, unsafe_allow_html=True)

    st.divider()

    # --- 3. Heroes ---
    st.write("### 🦸 Heroes")
    hero_cols = st.columns(3)
    col_idx = 0
    for h in setup['raw_heroes']:
        hero_html = get_hero_card_html(h)
        with hero_cols[col_idx % 3]:
            st.markdown(hero_html, unsafe_allow_html=True)
        col_idx += 1
        
    # Render any extras in setup['Heroes'] that aren't in raw_heroes
    raw_names = {h['hero'] for h in setup['raw_heroes']}
    for h_str in setup['Heroes']:
        if not any(h_str.startswith(name) for name in raw_names):
            extra_html = clean_html(f"""
            <div class='premium-card' style='height: 100%; border-style: dashed; border-color: rgba(255,255,255,0.2);'>
                <div class='card-header'>
                    <span class='badge-pill' style='background: rgba(255, 255, 255, 0.03); border: 1px solid #7f8c8d; color: #7f8c8d;'>📦 Hero Deck Extra</span>
                </div>
                <div class='card-title'>{h_str}</div>
            </div>
            """)
            with hero_cols[col_idx % 3]:
                st.markdown(extra_html, unsafe_allow_html=True)
            col_idx += 1
            
    # Wedding Heroes
    if setup.get('Wedding_Heroes'):
        st.write("#### 💍 Wedding Heroes (Set Aside)")
        wedding_html = clean_html("<div class='premium-card'><ul class='styled-list'>")
        for wh in setup['Wedding_Heroes']:
             wedding_html += f"<li>{wh}</li>"
        wedding_html += "</ul></div>"
        st.markdown(wedding_html, unsafe_allow_html=True)

    st.divider()

    # --- 4. Villain Deck Composition ---
    st.write("### 🃏 Villain Deck Composition")
    vd = setup['Villain_Deck_Setup']
    
    # Standard Counts
    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(clean_html(f"""
        <div class='metric-widget'>
            <div class='metric-label'>Scheme Twists</div>
            <div class='metric-val'>{vd['Scheme_Twists']}</div>
        </div>
        """), unsafe_allow_html=True)
    with m2:
        st.markdown(clean_html(f"""
        <div class='metric-widget'>
            <div class='metric-label'>Master Strikes</div>
            <div class='metric-val'>{vd['Master_Strikes']}</div>
        </div>
        """), unsafe_allow_html=True)
    with m3:
        st.markdown(clean_html(f"""
        <div class='metric-widget'>
            <div class='metric-label'>Bystanders</div>
            <div class='metric-val'>{vd['Bystanders']}</div>
        </div>
        """), unsafe_allow_html=True)

    st.markdown("#### ➕ Required Extras")
    
    # 1. Extra Cards (Sidekicks, Officers, etc.)
    extras_cols = st.columns(2)
    with extras_cols[0]:
        extras_left = []
        if vd.get('Sidekicks'): extras_left.append("<b>Sidekicks:</b> " + str(vd['Sidekicks']))
        if vd.get('Ambitions'): extras_left.append("<b>Ambitions:</b> " + str(vd['Ambitions']))
        if vd.get('Officers'): extras_left.append("<b>S.H.I.E.L.D. Officers:</b> " + str(vd['Officers']))
        if vd.get('Heroes_from_Hero_Deck'): extras_left.append("<b>Cards from Hero Deck:</b> " + str(vd['Heroes_from_Hero_Deck']) + " (Random)")
        
        if extras_left:
            st.markdown(clean_html("<div class='premium-card'><ul class='styled-list'>" + "".join("<li>" + item + "</li>" for item in extras_left) + "</ul></div>"), unsafe_allow_html=True)
        
    with extras_cols[1]:
        extras_right = []
        if vd.get('Tactics'): extras_right.append("<b>Mastermind Tactics:</b> " + str(vd['Tactics']))
        if vd.get('Quantum_Ambush'): extras_right.append("<b>Ambush Scheme:</b> Yes")
        
        if extras_right:
            st.markdown(clean_html("<div class='premium-card'><ul class='styled-list'>" + "".join("<li>" + item + "</li>" for item in extras_right) + "</ul></div>"), unsafe_allow_html=True)

    # 2. Specific Extra Heroes
    if setup['Villain_Deck_Heroes']:
        st.markdown("**🦸 Extra Heroes in Villain Deck:**")
        vd_heroes_html = clean_html("<div class='premium-card'><ul class='styled-list'>")
        for h in setup['Villain_Deck_Heroes']:
            vd_heroes_html += f"<li>{h}</li>"
        vd_heroes_html += "</ul></div>"
        st.markdown(vd_heroes_html, unsafe_allow_html=True)

    st.divider()

    # --- 5. Special Rules ---
    with st.expander("📝 Setup Notes & Special Rules", expanded=False):
        for line in setup['Scheme_Description']:
            if "Setup" in line or "Special Rules" in line:
                st.markdown(f"* {line}")

    st.divider()

    # --- 6. Export Setup ---
    with st.expander("📥 Export & Share Setup", expanded=False):
        md_lines = []
        md_lines.append("### 🦸 Legendary Smart Scenario Setup")
        md_lines.append(f"*   **Mastermind:** {setup['raw_mastermind']['name']} ({setup['raw_mastermind']['set']})")
        md_lines.append(f"*   **Scheme:** {setup['raw_scheme']['name']} ({setup['raw_scheme']['set']})")
        md_lines.append(f"*   **Villains:** {', '.join(setup['Villains'])}")
        md_lines.append(f"*   **Henchmen:** {', '.join(setup['Henchmen'])}")
        
        md_lines.append("*   **Heroes:**")
        for h in setup['Heroes']:
            md_lines.append(f"    * {h}")
            
        md_lines.append("*   **Villain Deck Composition:**")
        md_lines.append(f"    * Scheme Twists: {vd['Scheme_Twists']}")
        md_lines.append(f"    * Master Strikes: {vd['Master_Strikes']}")
        md_lines.append(f"    * Bystanders: {vd['Bystanders']}")
        
        if vd.get('Sidekicks'): md_lines.append(f"    * Sidekicks: {vd['Sidekicks']}")
        if vd.get('Officers'): md_lines.append(f"    * S.H.I.E.L.D. Officers: {vd['Officers']}")
        if setup['Villain_Deck_Heroes']: md_lines.append(f"    * Extra Heroes in Villain Deck: {', '.join(setup['Villain_Deck_Heroes'])}")
        
        md_text = "\n".join(md_lines)
        
        st.write("📋 **Markdown Checklist** (Copy to paste in BGG, Discord, or notes):")
        st.code(md_text, language="markdown")
        
        setup_json = json.dumps(setup, indent=2, ensure_ascii=False)
        st.download_button(
            label="📥 Download Setup JSON",
            data=setup_json,
            file_name=f"legendary_setup_{setup['raw_mastermind']['name'].lower().replace(' ', '_')}.json",
            mime="application/json",
            use_container_width=True
        )

if __name__ == "__main__":
    main()