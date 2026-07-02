import streamlit as st
from datetime import datetime
import sys
import os
import threading
import time
from streamlit.runtime.scriptrunner import add_script_run_ctx
import streamlit as st

# Pad toevoegen voor CrewAI
sys.path.append(os.path.join(os.getcwd(), "src"))
from Finance_tool.crew import FinanceCrew

# --- Generate Clean Dossier ---
def generate_clean_dossier(data):
    """Vertaalt alle verzamelde data naar een themathisch gestructureerd dossier voor de specifieke CrewAI-agents, inclusief 100% feitelijke pre-calculations."""
    
    # =================
    # PRE-CALCULATIONS
    # =================
    heeft_partner = data.get('fiscaal_partnerschap') == "Ja"
    
    # --- 1. GEBRUIKER INKOMENS-SPECIFICATIE (Harde Jaar- & Maandnormalisatie) ---
    jaar_loondienst_basis = 0.0
    jaar_vakantiegeld = 0.0
    jaar_13maand = 0.0
    jaar_bonus = 0.0
    jaar_overig_inkomen = 0.0
    
    for bron in data.get('inkomensbronnen', []):
        if bron == "Loondienst":
            maand_sal = float(data.get('bruto_maand', 0) or 0)
            jaar_loondienst_basis = maand_sal * 12
            if data.get('vakantiegeld') == "Ja": 
                jaar_vakantiegeld = jaar_loondienst_basis * 0.08
            if data.get('dertiende_maand') == "Ja": 
                jaar_13maand = maand_sal
            if data.get('heeft_bonus') == "Ja": 
                jaar_bonus = float(data.get('bonus_bedrag', 0) or 0)
        elif bron == "Zzp":
            # ZZP winst wordt per jaar opgegeven
            jaar_overig_inkomen += float(data.get('winst_3_jaar', 0) or 0)
        elif bron == "Inkomsten uit B.V./N.V.":
            # DGA salaris en BV winst worden per jaar opgegeven
            jaar_overig_inkomen += float(data.get('dga_salaris', 0) or 0) + float(data.get('dividend', 0) or 0)
        else:
            keys = {"Uitkering (WW, WIA, Bijstand)": "uitkering_bedrag", "Vermogen (Huur, Dividend)": "vermogen_inkomen", "Pensioen": "pensioen_inkomen", "Alimentatie (Ontvangen)": "alimentatie_inkomen", "Overig": "overig_inkomen"}
            # Overige bronnen zijn per maand ingevuld, dus naar jaarbasis rekenen
            jaar_overig_inkomen += float(data.get(keys.get(bron, ""), 0) or 0) * 12

    fiscaal_jaarinkomen_gebruiker = jaar_loondienst_basis + jaar_vakantiegeld + jaar_13maand + jaar_bonus + jaar_overig_inkomen
    bruto_pm_gebruiker = fiscaal_jaarinkomen_gebruiker / 12

    # --- 2. PARTNER INKOMENS-SPECIFICATIE (Indien van toepassing) ---
    jaar_loondienst_basis_fp = 0.0
    jaar_vakantiegeld_fp = 0.0
    jaar_13maand_fp = 0.0
    jaar_bonus_fp = 0.0
    jaar_overig_inkomen_fp = 0.0
    fiscaal_jaarinkomen_partner = 0.0
    bruto_pm_partner = 0.0
    
    if heeft_partner:
        for bron in data.get('inkomensbronnen_fp', []):
            if bron == "Loondienst":
                maand_sal_fp = float(data.get('bruto_maand_fp', 0) or 0)
                jaar_loondienst_basis_fp = maand_sal_fp * 12
                if data.get('vakantiegeld_fp') == "Ja": 
                    jaar_vakantiegeld_fp = jaar_loondienst_basis_fp * 0.08
                if data.get('dertiende_maand_fp') == "Ja": 
                    jaar_13maand_fp = maand_sal_fp
                if data.get('heeft_bonus_fp') == "Ja": 
                    jaar_bonus_fp = float(data.get('bonus_bedrag_fp', 0) or 0)
            elif bron == "Zzp": 
                jaar_overig_inkomen_fp += float(data.get('winst_3_jaar_fp', 0) or 0)
            elif bron == "Inkomsten uit B.V./N.V.":
                jaar_overig_inkomen_fp += float(data.get('dga_salaris_fp', 0) or 0) + float(data.get('dividend', 0) or 0)
            else:
                keys_fp = {"Uitkering (WW, WIA, Bijstand)": "uitkering_bedrag_fp", "Vermogen (Huur, Dividend)": "vermogen_inkomen_fp", "Pensioen": "pensioen_inkomen_fp", "Alimentatie (Ontvangen)": "alimentatie_inkomen_fp", "Overig": "overig_inkomen_fp"}
                jaar_overig_inkomen_fp += float(data.get(keys_fp.get(bron, ""), 0) or 0) * 12

        fiscaal_jaarinkomen_partner = jaar_loondienst_basis_fp + jaar_vakantiegeld_fp + jaar_13maand_fp + jaar_bonus_fp + jaar_overig_inkomen_fp
        bruto_pm_partner = fiscaal_jaarinkomen_partner / 12

    totaal_bruto_pm = bruto_pm_gebruiker + bruto_pm_partner
    totaal_toetsingsinkomen_jaar = fiscaal_jaarinkomen_gebruiker + fiscaal_jaarinkomen_partner

    # =========================================================================
    # HARDCODED NETTO ENGINE 2026 (Inclusief AOW-status, AHK, AK, OK & ZVW)
    # =========================================================================
    def _bereken_netto_jaarinkomen(jaarinkomen, heeft_arbeid, zvw_plichtig_inkomen, aftrekposten, aow_status="jonger"):
        if jaarinkomen <= 0:
            return 0.0
        
        belastbaar_inkomen = max(0.0, jaarinkomen - aftrekposten)
        
        # 1. Bruto Box 1 Belasting (Schijven 2026 afhankelijk van AOW-status)
        bruto_belasting = 0.0
        
        if aow_status == "jonger":
            if belastbaar_inkomen <= 38883:
                bruto_belasting = belastbaar_inkomen * 0.3575
            elif belastbaar_inkomen <= 78426:
                bruto_belasting = 13900.0 + ((belastbaar_inkomen - 38883) * 0.3756)
            else:
                bruto_belasting = 28752.0 + ((belastbaar_inkomen - 78426) * 0.4950)
                
        elif aow_status == "aow_vanaf_1946":
            if belastbaar_inkomen <= 38883:
                bruto_belasting = belastbaar_inkomen * 0.1785
            elif belastbaar_inkomen <= 78426:
                bruto_belasting = 6940.0 + ((belastbaar_inkomen - 38883) * 0.3756)
            else:
                bruto_belasting = 21792.0 + ((belastbaar_inkomen - 78426) * 0.4950)
                
        elif aow_status == "aow_voor_1946":
            if belastbaar_inkomen <= 41123:
                bruto_belasting = belastbaar_inkomen * 0.1785
            elif belastbaar_inkomen <= 78426:
                bruto_belasting = 7340.0 + ((belastbaar_inkomen - 41123) * 0.3756)
            else:
                bruto_belasting = 21351.0 + ((belastbaar_inkomen - 78426) * 0.4950)
        
        # 2. Algemene Heffingskorting (AHK) + Afbouw vanaf €29.736
        if aow_status == "jonger":
            max_ahk = 3115.0
            ahk = max_ahk - ((belastbaar_inkomen - 29736) * 0.06398) if belastbaar_inkomen > 29736 else max_ahk
        else:
            max_ahk = 1556.0
            ahk = max_ahk - ((belastbaar_inkomen - 29736) * 0.03195) if belastbaar_inkomen > 29736 else max_ahk
        ahk = max(0.0, ahk)
        
        # 3. Arbeidskorting (AK) + Afbouw vanaf €45.592
        ak = 0.0
        if heeft_arbeid:
            if aow_status == "jonger":
                max_ak = 5685.0
                ak = max_ak - ((belastbaar_inkomen - 45592) * 0.0651) if belastbaar_inkomen > 45592 else max_ak
            else:
                max_ak = 2840.0
                ak = max_ak - ((belastbaar_inkomen - 45592) * 0.0325) if belastbaar_inkomen > 45592 else max_ak
            ak = max(0.0, ak)
            
        # 4. Ouderenkorting + Afbouw vanaf €46.002 (Alleen van toepassing vanaf AOW-leeftijd)
        ouderenkorting = 0.0
        if aow_status != "jonger":
            max_ok = 2067.0
            ouderenkorting = max_ok - ((belastbaar_inkomen - 46002) * 0.15) if belastbaar_inkomen > 46002 else max_ok
            ouderenkorting = max(0.0, ouderenkorting)
            
        # 5. Netto inkomstenbelasting (Kortingen kunnen belasting niet onder €0 drukken)
        totale_kortingen = ahk + ak + ouderenkorting
        netto_belasting = max(0.0, bruto_belasting - totale_kortingen)
        
        # 6. ZVW-Bijdrage berekenen (4,85% over niet-loondienst deel, max €3.851 per jaar)
        zvw_bijdrage = min(3851.0, zvw_plichtig_inkomen * 0.0485)
        
        return max(0.0, jaarinkomen - netto_belasting - zvw_bijdrage)
    # Inlezen van de persoonsgebonden aftrekposten uit data (or 0 bescherming)
    aftrekposten_gebruiker = float((data.get('alimentatie_betaald_bedrag', 0) * 12) + data.get('aftrek_bedrag', 0) or 0)
    aftrekposten_partner = float((data.get('alimentatie_betaald_bedrag_fp', 0) * 12) + data.get('aftrek_bedrag_fp', 0) or 0)

    # =========================================================================
    # AUTOMATISCHE AOW-CONSTATERING OP BASIS VAN LEEFTIJD (REFERENTIEJAAR 2026)
    # =========================================================================
    def _bepaal_aow_status(leeftijd_val):
        try:
            lf = int(leeftijd_val)
        except (ValueError, TypeError):
            return "jonger"
            
        if lf < 67:
            return "jonger"
        # Bereken dynamisch het geboortejaar op basis van het huidige klokjaar
        huidig_jaar = datetime.now().year
        geboortejaar = huidig_jaar - lf
        
        # De harde grens van de Belastingdienst blijft gebaseerd op het jaartal 1946
        if geboortejaar < 1946:
            return "aow_voor_1946"
        else:
            return "aow_vanaf_1946"

    # AOW-status bepalen voor de gebruiker en partner
    aow_status_gebruiker = _bepaal_aow_status(data.get('leeftijd', 0))
    aow_status_partner = _bepaal_aow_status(data.get('leeftijd_fp', 0)) if heeft_partner else "jonger"

    # Toets of de gebruiker en partner actieve arbeidsinkomsten hebben voor de Arbeidskorting
    arbeidsbronnen = ["Loondienst", "Zzp", "Inkomsten uit B.V./N.V."]
    heeft_arbeid_gebruiker = any(b in arbeidsbronnen for b in data.get('inkomensbronnen', []))
    
    # Berekening netto maandinkomen met de dynamische AOW-status
    netto_pm_gebruiker = _bereken_netto_jaarinkomen(
        fiscaal_jaarinkomen_gebruiker, 
        heeft_arbeid_gebruiker, 
        jaar_overig_inkomen,
        aftrekposten_gebruiker,
        aow_status_gebruiker
    ) / 12
    
    netto_pm_partner = 0.0
    if heeft_partner:
        heeft_arbeid_partner = any(b in arbeidsbronnen for b in data.get('inkomensbronnen_fp', []))
        netto_pm_partner = _bereken_netto_jaarinkomen(
            fiscaal_jaarinkomen_partner, 
            heeft_arbeid_partner, 
            jaar_overig_inkomen_fp,
            aftrekposten_partner,
            aow_status_partner
        ) / 12
        
    totaal_netto_pm = netto_pm_gebruiker + netto_pm_partner
    # =========================================================================
    # --- 3. NETTO VASTE LASTEN BEREKENING (p/m) ---
    # =========================================================================
    netto_vaste_lasten_pm = 0.0
    woon = data.get('woonsituatie')
    if woon == "Huurwoning":
        netto_vaste_lasten_pm += float(data.get('huurprijs', 0) or 0) + float(data.get('servicekosten', 0) or 0)
    elif woon == "Inwonend":
        netto_vaste_lasten_pm += float(data.get('kostgeld', 0) or 0)
    elif woon == "Koopwoning":
        for huis in data.get('huizen_lijst', []):
            netto_vaste_lasten_pm += float(huis.get('hypo_maandlast_bruto', 0) or 0)
            netto_vaste_lasten_pm += float(huis.get('vve_bijdrage', 0) or 0)
            if huis.get('heeft_erfpacht'): 
                netto_vaste_lasten_pm += float(huis.get('erfpacht_canon', 0) or 0) / 12

    if woon != "Inwonend":
        netto_vaste_lasten_pm += float(data.get('energie_lasten', 0) or 0) + float(data.get('water_lasten', 0) or 0)
        netto_vaste_lasten_pm += float(data.get('gemeente_lasten_kwartaal', 0) or 0) / 3

    total_overig_verzekeringen = sum(float(v) for v in data.get('verzekeringen_details', {}).values())
    netto_vaste_lasten_pm += float(data.get('uitgave_zorg', 0) or 0) + float(data.get('uitgave_telecom', 0) or 0) + total_overig_verzekeringen
    netto_vaste_lasten_pm += float(data.get('alimentatie_betaald_bedrag', 0) or 0) if data.get('betaalt_alimentatie') == "Ja" else 0
    netto_vaste_lasten_pm += float(data.get('alimentatie_betaald_bedrag_fp', 0) or 0) if data.get('betaalt_alimentatie_fp') == "Ja" else 0
    netto_vaste_lasten_pm += float(data.get('consumptief_maandlast', 0) or 0) if data.get('consumptief_schuld') else 0

    for auto in data.get('autos_lijst', []):
        if "lease" in auto.get('situatie', '').lower():
            netto_vaste_lasten_pm += float(auto.get('lease_bedrag', 0) or 0)

    # --- 4. NETTO FLEXIBELE LASTEN BEREKENING (p/m) ---
    netto_flex_lasten_pm = sum([
        float(data.get('uitgave_abonnementen', 0) or 0),
        float(data.get('boodschappen', 0) or 0),
        float(data.get('vervoer', 0) or 0),
        float(data.get('vakantie', 0) or 0),
        float(data.get('vrije_tijd', 0) or 0)
    ])

    # --- 5. OVERIGE KERNCIJFERS (Vermogen, Schulden & Koopwens) ---
    totaal_box3 = float(data.get('buffer', 0) or 0) + float(data.get('beleggingen', 0) or 0) + float(data.get('overig_vermogen', 0) or 0)
    schuld_duo = float(data.get('studie_bedrag', 0) or 0) + float(data.get('studie_bedrag_fp', 0) or 0)
    schuld_cons = float(data.get('consumptief_bedrag', 0) or 0) if data.get('consumptief_schuld') else 0.0
    financieringsbehoefte = max(0.0, float(data.get('koop_prijs', 0) or 0) - float(data.get('koop_eigen_geld', 0) or 0)) if data.get('koopwens') else 0.0



    # ==========================================
    # DOSSIER OPBOUW (MET EXPLICIETE TIJDSAANDUIDINGEN)
    # ==========================================
    dossier = "--- VOLLEDIG FINANCIEEL DOSSIER GEBRUIKER ---\n\n"
    
    # --- [0. GEDEELDE CONTEXT & KERNCIJFERS] ---
    dossier += "## [0. GEDEELDE CONTEXT & KERNCIJFERS]\n"
    dossier += "LET OP AI: Vergelijk het BRUTO inkomen NOOIT direct met de NETTO uitgaven. Houd rekening met inkomstenbelasting.\n"
    dossier += f"- Datum van analyse: {data.get('datum')}\n"
    dossier += f"- Referentie: {data.get('klant_referentie', 'Niet opgegeven')} | Leeftijd: {data.get('leeftijd')} jaar | Burgerlijke staat: {data.get('burgerlijke_staat')}\n"
    dossier += f"- Hoofddoel: {data.get('belangrijkste_doel')}\n"
    dossier += f"- Grootste zorg: {data.get('grootste_zorg')}\n\n"
    dossier += f"- Fiscaal partnerschap: {'Ja' if heeft_partner else 'Nee'}\n"
    if data.get('kinderen') == "Ja":
        leeftijden = data.get('leeftijd_categorie', [])
        leeftijden_str = ", ".join(leeftijden) if isinstance(leeftijden, list) else leeftijden
        dossier += f"- Kinderen: Ja, {data.get('aantal_kinderen')} kind(eren) in de categorie {leeftijden_str}\n\n"
    else:
        dossier += "- Kinderen: Nee\n\n"

    dossier += f"- Totaal BRUTO Inkomen Huishouden (MAANDBASIS): €{totaal_bruto_pm:.2f} p/m\n"
    dossier += f"- Totaal GESCHAT NETTO Inkomen Huishouden (MAANDBASIS): €{totaal_netto_pm:.2f} p/m (Gebruiker: €{netto_pm_gebruiker:.2f} p/m, Partner: €{netto_pm_partner:.2f} p/m)\n"
    dossier += f"- Totaal TOETSINGSINKOMEN Huishouden (JAARBASIS): €{totaal_toetsingsinkomen_jaar:.2f} p/j (Gebruiker: €{fiscaal_jaarinkomen_gebruiker:.2f} p/j, Partner: €{fiscaal_jaarinkomen_partner:.2f} p/j)\n"
    dossier += f"- Totale NETTO Vaste Lasten: €{netto_vaste_lasten_pm:.2f} p/m\n"
    dossier += f"- Totale NETTO Flexibele Lasten: €{netto_flex_lasten_pm:.2f} p/m\n"
    dossier += f"- Totale NETTO Uitgaven (Vast + Flex): €{(netto_vaste_lasten_pm + netto_flex_lasten_pm):.2f} p/m\n"
    dossier += f"- Totaal Box 3 Vermogen: €{totaal_box3:.2f}\n"
    dossier += f"- Totale Niet-Hypothecaire Schuld: €{(schuld_duo + schuld_cons):.2f}\n"
    if data.get('koopwens'): dossier += f"- Actieve Koopwens Financieringsbehoefte: €{financieringsbehoefte:.2f}\n"

    particulier_bronnen = ["Loondienst", "Uitkering (WW, WIA, Bijstand)", "Vermogen (Huur, Dividend)", "Pensioen", "Alimentatie (Ontvangen)", "Overig"]
    zakelijk_bronnen = ["Zzp", "Inkomsten uit B.V./N.V."]

    # --- [1. DOMEIN: INKOMEN, TOESLAGEN & FISCALITEIT] ---
    dossier += "\n## [1. DOMEIN: INKOMEN, TOESLAGEN & FISCALITEIT]\n"
    dossier += "### Gebruiker (Particulier Inkomen Breakdown)\n"
    bronnen = data.get('inkomensbronnen', [])
    heeft_particulier = False
    for bron in bronnen:
        if bron in particulier_bronnen:
            heeft_particulier = True
            if bron == "Loondienst":
                vak = 'Ja' if data.get('vakantiegeld') == "Ja" else 'Nee'
                m13 = 'Ja' if data.get('dertiende_maand') == "Ja" else 'Nee'
                dossier += f"* **Loondienst Specificatie (Harde euro's):**\n"
                dossier += f"    - Kaal bruto salaris: €{float(data.get('bruto_maand', 0) or 0):.2f} p/m (Jaarbasis basisloon: €{jaar_loondienst_basis:.2f} p/j)\n"
                dossier += f"    - Vakantiegeld: €{jaar_vakantiegeld:.2f} p/j (Opbouw geregistreerd: {vak})\n"
                dossier += f"    - 13e Maand / Eindejaarsuitkering: €{jaar_13maand:.2f} p/j (Opbouw geregistreerd: {m13})\n"
                dossier += f"    - Structurele Bonus / Overwerk: €{jaar_bonus:.2f} p/j\n"
                dossier += f"    - TOTAAL BEREKEND FISCAAL JAARINKOMEN BOX 1 (GEBRUIKER): €{fiscaal_jaarinkomen_gebruiker:.2f} p/j\n"
            else:
                overige_bron_keys = {"Uitkering (WW, WIA, Bijstand)": "uitkering_bedrag", "Vermogen (Huur, Dividend)": "vermogen_inkomen", "Pensioen": "pensioen_inkomen", "Alimentatie (Ontvangen)": "alimentatie_inkomen", "Overig": "overig_inkomen"}
                key = overige_bron_keys.get(bron)
                if key: 
                    val_pm = float(data.get(key, 0) or 0)
                    dossier += f"* **{bron}:** €{val_pm:.2f} p/m (Jaarbasis: €{(val_pm * 12):.2f} p/j)\n"
    if not heeft_particulier: dossier += "- Geen particuliere inkomensbronnen.\n"

    alim_betaald = f" (€{data.get('alimentatie_betaald_bedrag', 0) or 0} p/m)" if data.get('betaalt_alimentatie') == "Ja" else "Nee"
    dossier += f"- Betaalt partneralimentatie: {alim_betaald}\n"
    dossier += f"- **Berekend Netto Maandinkomen (Gebruiker):** €{netto_pm_gebruiker:.2f} p/m\n"
    if heeft_partner:
        dossier += "\n### Partner (Particulier Inkomen Breakdown)\n"
        bronnen_fp = data.get('inkomensbronnen_fp', [])
        heeft_particulier_fp = False
        for bron in bronnen_fp:
            if bron in particulier_bronnen:
                heeft_particulier_fp = True
                if bron == "Loondienst":
                    vak_fp = 'Ja' if data.get('vakantiegeld_fp') == "Ja" else 'Nee'
                    m13_fp = 'Ja' if data.get('dertiende_maand_fp') == "Ja" else 'Nee'
                    dossier += f"* **Loondienst Partner Specificatie (Harde euro's):**\n"
                    dossier += f"    - Kaal bruto salaris partner: €{float(data.get('bruto_maand_fp', 0) or 0):.2f} p/m (Jaarbasis basisloon: €{jaar_loondienst_basis_fp:.2f} p/j)\n"
                    dossier += f"    - Vakantiegeld partner: €{jaar_vakantiegeld_fp:.2f} p/j (Opbouw geregistreerd: {vak_fp})\n"
                    dossier += f"    - 13e Maand partner: €{jaar_13maand_fp:.2f} p/j (Opbouw geregistreerd: {m13_fp})\n"
                    dossier += f"    - Structurele Bonus partner: €{jaar_bonus_fp:.2f} p/j\n"
                    dossier += f"    - TOTAAL BEREKEND FISCAAL JAARINKOMEN BOX 1 (PARTNER): €{fiscaal_jaarinkomen_partner:.2f} p/j\n"
                else:
                    overige_bron_keys_fp = {"Uitkering (WW, WIA, Bijstand)": "uitkering_bedrag_fp", "Vermogen (Huur, Dividend)": "vermogen_inkomen_fp", "Pensioen": "pensioen_inkomen_fp", "Alimentatie (Ontvangen)": "alimentatie_inkomen_fp", "Overig": "overig_inkomen_fp"}
                    key_fp = overige_bron_keys_fp.get(bron)
                    if key_fp: 
                        val_pm_fp = float(data.get(key_fp, 0) or 0)
                        dossier += f"* **{bron} (Partner):** €{val_pm_fp:.2f} p/m (Jaarbasis: €{(val_pm_fp * 12):.2f} p/j)\n"
        if not heeft_particulier_fp: dossier += "- Geen particuliere inkomensbronnen voor partner.\n"
        alim_betaald_fp = f" (€{data.get('alimentatie_betaald_bedrag_fp', 0) or 0} p/m)" if data.get('betaalt_alimentatie_fp') == "Ja" else "Nee"
        dossier += f"- Betaalt partneralimentatie (Partner): {alim_betaald_fp}\n"
        dossier += f"- **Berekend Netto Maandinkomen (Partner):** €{netto_pm_partner:.2f} p/m\n"
    toeslagen = data.get('toeslagen', [])
    toeslagen_fp = data.get('toeslagen_fp', [])
    alle_toeslagen = list(set(toeslagen + toeslagen_fp))
    dossier += f"\n- Actieve Toeslagen in huishouden: {', '.join(alle_toeslagen) if alle_toeslagen else 'Geen'}\n"

    # --- [2. DOMEIN: ONDERNEMEN, DGA & MOBILITEIT] ---
    dossier += "\n## [2. DOMEIN: ONDERNEMEN, DGA & MOBILITEIT]\n"
    dossier += "### Zakelijk Inkomen\n"
    heeft_zakelijk = False
    
    for bron in bronnen:
        if bron in zakelijk_bronnen:
            heeft_zakelijk = True
            if bron == "Zzp": dossier += f"* **Zzp / Eenmanszaak (Gebruiker):** €{data.get('winst_3_jaar', 0)} winst p/j (gem. 3jr) | Reserves: €{data.get('zakelijke_reserves', 0)}\n"
            elif bron == "Inkomsten uit B.V./N.V.": dossier += f"* **B.V./N.V. (Gebruiker):** €{data.get('dga_salaris', 0)} salaris p/j | €{data.get('bruto_winst', 0)} winst p/j | €{data.get('dividend'), 0} uitgekeerd dividend p/j\n"
            
    if heeft_partner:
        for bron in data.get('inkomensbronnen_fp', []):
            if bron in zakelijk_bronnen:
                heeft_zakelijk = True
                if bron == "Zzp": dossier += f"* **Zzp / Eenmanszaak (Partner):** €{data.get('winst_3_jaar_fp', 0)} winst p/j (gem. 3jr) | Reserves: €{data.get('zakelijke_reserves_fp', 0)}\n"
                elif bron == "Inkomsten uit B.V./N.V.": dossier += f"* **B.V./N.V. (Partner):** €{data.get('dga_salaris_fp', 0)} salaris p/j | €{data.get('bruto_winst_fp', 0)} winst p/j | €{data.get('dividend_fp'), 0} uitgekeerd dividend p/j\n"
                
    if not heeft_zakelijk: dossier += "- Geen zakelijke inkomensbronnen (Geen ZZP/DGA).\n"

    dossier += "\n### Mobiliteit & Voertuigen\n"
    aantal_autos = data.get('aantal_autos', 0)
    if aantal_autos > 0:
        dossier += f"- Totaal aantal voertuigen: {aantal_autos}\n"
        for i, auto in enumerate(data.get('autos_lijst', []), 1):
            sit = auto.get('situatie', 'Onbekend')
            elek = auto.get('is_elektrisch', 'Nee')
            dossier += f"  * Auto {i}: {sit} (Bouwjaar: {auto.get('bouwjaar')} | Elektrisch: {elek})\n"
            if "lease" in sit.lower(): dossier += f"    - Leasebedrag: €{auto.get('lease_bedrag', 0)} p/m | Contracthouder: {auto.get('contracthouder')}\n"
            else: dossier += f"    - Geschatte dagwaarde: €{float(auto.get('waarde_prive', 0) or 0):.2f}\n"
    else:
        dossier += "- Geen auto's of leasevoertuigen opgegeven.\n"

    # --- [3. DOMEIN: VERMOGEN, PENSIOEN & ESTATE PLANNING] ---
    dossier += "\n## [3. DOMEIN: VERMOGEN, PENSIOEN & ESTATE PLANNING]\n"
    dossier += "### Box 3 Vermogen\n"
    dossier += f"- Spaarbuffer: €{data.get('buffer', 0)}\n"
    dossier += f"- Beleggingen: €{data.get('beleggingen', 0)} (Ervaring: {'Ja' if data.get('ervaring_beleggen') else 'Nee'})\n"
    dossier += f"- Overig vermogen (Crypto/Goud): €{data.get('overig_vermogen', 0)}\n"
    
    dossier += "\n### Schulden & BKR\n"
    if data.get('heeft_studie'): dossier += f"- DUO Studieschuld (Gebruiker): €{data.get('studie_bedrag', 0)} | Stelsel: {data.get('studie_stelsel')} | Rente: {data.get('studie_rente')}% | Resterende looptijd: {data.get('studie_looptijd')} mnd\n"
    if heeft_partner and data.get('heeft_studie_fp'): dossier += f"- DUO Studieschuld (Partner): €{data.get('studie_bedrag_fp', 0)} | Stelsel: {data.get('studie_stelsel_fp')} | Rente: {data.get('studie_rente_fp')}% | Resterende looptijd: {data.get('studie_looptijd_fp')} mnd\n"
    if not data.get('heeft_studie') and not (heeft_partner and data.get('heeft_studie_fp')): dossier += "- Geen studieschulden bij DUO.\n"
        
    if data.get('consumptief_schuld'): dossier += f"- Consumptief (Leningen/Krediet): €{data.get('consumptief_bedrag', 0)} | Totale maandlast: €{data.get('consumptief_maandlast', 0)} | Gem. rente: {data.get('consumptief_rente')}%\n"
    else: dossier += "- Geen consumptieve schulden.\n"
        
    dossier += f"- Actieve BKR Achterstanden: {'Ja' if data.get('bkr_achterstand') else 'Nee'}\n"

    dossier += "\n### Pensioen (Oudedagsvoorziening)\n"
    dossier += f"- Gewenste pensioenleeftijd: {data.get('pensioenleeftijd', 67)} jaar\n"
    dossier += f"- Pensioenopbouw via werkgever: {'Ja' if data.get('pensioen_werkgever') else 'Nee'}\n"
    if data.get('heeft_lijfrente'):
        dossier += f"- Aanvullende lijfrente: Ja | Saldo: €{data.get('lijfrente_saldo', 0)} | Jaarruimte benut: {data.get('jaarruimte_status', 'Nee')}\n"
    else:
        dossier += "- Aanvullende lijfrente: Nee\n"

    # --- [4. DOMEIN: WONEN & VASTGOED] ---
    dossier += "\n## [4. DOMEIN: WONEN & VASTGOED]\n"
    dossier += "### Huidige Woonsituatie\n"
    dossier += f"- Situation: {woon}\n"
    if woon == "Huurwoning":
        dossier += f"  * Kale huur: €{data.get('huurprijs')} p/m | Servicekosten: €{data.get('servicekosten')} p/m\n"
        dossier += f"  * Type: {'Sociale huur' if data.get('sociale_huur') else 'Vrije sector'}\n"
    elif woon == "Koopwoning":
        huizen = data.get('huizen_lijst', [])
        dossier += f"  * Aantal koopwoningen in bezit: {data.get('aantal_huizen', 0)}\n"
        for idx, huis in enumerate(huizen, 1):
            dossier += f"\n  **Woning {idx}:**\n"
            dossier += f"  * Type: {huis.get('type_woning')} | WOZ-waarde: €{huis.get('woz_waarde')} | Energielabel: {huis.get('energielabel')}\n"
            dossier += f"  * Bouwperiode: {huis.get('bouwjaar_periode')}\n"
            if huis.get('heeft_hypotheek'):
                dossier += f"  * Hypotheek (bruto maandlast): €{huis.get('hypo_maandlast_bruto', 0)} p/m\n"
                vormen = huis.get('gekozen_vormen', [])
                if vormen:
                    dossier += f"  * Gekozen hypotheekvormen: {', '.join(vormen)}\n"
                    for vorm in vormen:
                        details = huis.get('vormen_details', {}).get(vorm, {})
                        dossier += f"    - {vorm}: Restschuld €{details.get('restschuld', 0)} | Rente {details.get('rente', 0)}% | Rente vast {details.get('rentevaste_periode', 0)} jr\n"
            else:
                dossier += "  * Hypotheek: Geen\n"
            
            if huis.get('heeft_erfpacht'): dossier += f"  * Erfpachtcanon: €{huis.get('erfpacht_canon')} p/j\n"
            if huis.get('vve_bijdrage'): dossier += f"  * VvE bijdrage: €{huis.get('vve_bijdrage')} p/m\n"
    elif woon == "Inwonend":
        dossier += f"  * Kostgeld: €{data.get('kostgeld')} p/m\n"

    if woon != "Inwonend":
        dossier += f"\n- Nutsvoorzieningen: Gas/Licht €{data.get('energie_lasten', 0)} p/m, Water €{data.get('water_lasten', 0)} p/m\n"
        dossier += f"- Gemeentelijke lasten: €{data.get('gemeente_lasten_kwartaal', 0)} per kwartaal\n"

    dossier += "\n### Toekomstige Woonwens\n"
    if data.get('koopwens'):
        dossier += "- STATUS: Gebruiker heeft een actieve koopwens.\n"
        dossier += f"  * Termijn: {data.get('koop_termijn')}\n"
        dossier += f"  * Beoogde koopprijs: €{data.get('koop_prijs')}\n"
        dossier += f"  * Beoogde eigen geld inleg: €{data.get('koop_eigen_geld')}\n"
        dossier += f"  * Type bouw: {data.get('koop_bouwtype')}\n"
    else:
        dossier += "- Geen actieve koopwens op dit moment.\n"

    # --- [5. DOMEIN: STRATEGIE, BUDGET & ZORG] ---
    dossier += "\n## [5. DOMEIN: STRATEGIE, BUDGET & ZORG]\n"
    dossier += "### Doelen & Visie\n"
    dossier += f"- Hoofddoel: {data.get('belangrijkste_doel')}\n"
    dossier += f"- Grootste zorg: {data.get('grootste_zorg')}\n"

    dossier += "\n### Budget: Vaste Lasten & Zorg\n"
    dossier += f"- Zorgverzekering: €{data.get('uitgave_zorg', 0)} p/m\n"
    dossier += f"- Telecom (Internet/Mobiel): €{data.get('uitgave_telecom', 0)} p/m\n"
    gekozen_verz = data.get('gekozen_verzekeringen', [])
    dossier += f"- Overige verzekeringen: Totaal €{total_overig_verzekeringen} p/m\n"
    if gekozen_verz:
        verz_details = data.get('verzekeringen_details', {})
        for vz in gekozen_verz:
            dossier += f"  * {vz}: €{verz_details.get(vz, 0)} p/m\n"

    dossier += "\n### Budget: Flexibele Uitgaven\n"
    dossier += f"- Abonnementen: €{data.get('uitgave_abonnementen', 0)} p/m\n"
    dossier += f"- Boodschappen: €{data.get('boodschappen', 0)} p/m\n"
    dossier += f"- Vervoer (Benzine/OV): €{data.get('vervoer', 0)} p/m\n"
    dossier += f"- Vakantie & Reizen (maandgemiddelde): €{data.get('vakantie', 0)} p/m\n"
    dossier += f"- Vrije tijd & Hobby's: €{data.get('vrije_tijd', 0)} p/m\n"

    dossier += "\n### Financieel Gedrag & Lifestyle\n"
    lekken = data.get('lekken', [])
    dossier += f"- Vermoedelijke financiële lekken: {'Ja' if lekken else 'Nee'}\n"
    if lekken:
        dossier += f"  * Vermoedelijke oorzaken: {', '.join(lekken)}\n"
        dossier += f"    - Geschat lekbedrag: €{float(data.get('lekbedrag', 0) or 0):.2f} p/m\n"

    if data.get('overige_uitgaven_tekst'):
        dossier += f"- Toelichting klant op levensstijl (AI: Respecteer bewuste hobby-keuzes): \"{data.get('overige_uitgaven_tekst')}\"\n"
        
    grip = data.get('schatting_overschot_status', 'Geen idee')
    dossier += f"- Subjectief gevoel van grip: {grip}\n"
    if grip == "Ik hou geld over": dossier += f"  * Geschat maandelijks overschot (klant): €{data.get('schatting_overschot_bedrag', 0)}\n"
    elif grip == "Ik kom maandelijks tekort": dossier += f"  * Geschat maandelijks tekort (klant): €{data.get('schatting_tekort_bedrag', 0)}\n"

    return dossier
# --- CONFIGURATIE ---
st.set_page_config(page_title="Financieel Coach", page_icon="💰", layout="centered")

# --- INITIALISATIE SESSION STATE ---
if 'step' not in st.session_state:
    st.session_state.step = 1
if 'data' not in st.session_state:
    st.session_state.data = {}

st.title("🤖 Jouw AI Financiële Coach")

# --- Loading (Genereren Scherm) ---
if st.session_state.get('generating'):
    st.header("⏳ Rapport wordt gegenereerd...")
    st.info("Je financiële dossier is succesvol overgedragen aan onze AI-experts. Ze analyseren nu je situatie. Dit duurt ongeveer 1 tot 2 minuten. Een moment geduld alsjeblieft, sluit deze pagina niet af!")
    
    # 1. Voorbereiding
    schoon_dossier = generate_clean_dossier(st.session_state.data)
    finance_crew = FinanceCrew()
    inputs = {'user_input': schoon_dossier}

    # 2. De AI-functie voor de achtergrond
    def run_ai_analysis(inputs_dict):
        try:
            # De volledige kickoff uitvoeren
            result = finance_crew.crew().kickoff(inputs=inputs_dict)
            
            # Sla het eindrapport op
            st.session_state.generated_report = result.raw
            
            # Sla de individuele outputs van alle taken op in een dictionary
            expert_outputs = {}
            for task_output in result.tasks_output:
                name = task_output.description.split('\n')[0][:30]
                expert_outputs[name] = task_output.raw
                
            st.session_state.expert_analyses = expert_outputs
    
        except Exception as e:
            st.session_state.ai_error = str(e)

    # 3. Start de thread met de juiste context
    if 'ai_thread_started' not in st.session_state:
        report_thread = threading.Thread(target=run_ai_analysis, args=(inputs,))
        add_script_run_ctx(report_thread) 
        report_thread.start()
        st.session_state.ai_thread_started = True

    # 4. De voortgangsbalk (Main Thread)
    progress_placeholder = st.empty()
    progress_text = "De AI-Coaches analyseren je situatie..."
    start_time = time.time()
    
    while 'generated_report' not in st.session_state and 'ai_error' not in st.session_state:
        elapsed = int(time.time() - start_time)
        progress_val = min(elapsed / 90.0, 0.95)
        progress_placeholder.progress(progress_val, text=f"{progress_text} ({elapsed}s)")
        time.sleep(0.5)

    # 5. Schoonmaken en overgang naar finished state
    progress_placeholder.empty()
    
    if 'ai_error' in st.session_state:
        st.error(f"Er is iets misgegaan: {st.session_state.ai_error}")
        if 'ai_thread_started' in st.session_state:
            del st.session_state.ai_thread_started
        st.stop()
    
    st.session_state.generating = False
    st.session_state.finished = True
    st.rerun()

# --- Finished (Rapportage Scherm) ---
elif st.session_state.get('finished'):
    st.header("📊 Jouw Persoonlijk Financieel Rapport")
    st.markdown("---")
    st.markdown(st.session_state.generated_report)
    
    if 'expert_analyses' in st.session_state:
            with st.expander("🕵️ Bekijk de gedetailleerde analyses per expert"):
                st.info("Hieronder zie je de ruwe input die de experts hebben aangeleverd aan de eindredacteur.")
            
                # We maken tabbladen voor elke expert zodat het overzichtelijk blijft
                expert_names = list(st.session_state.expert_analyses.keys())
                tabs = st.tabs(expert_names)
                
                for i, name in enumerate(expert_names):
                    with tabs[i]:
                        st.markdown(st.session_state.expert_analyses[name])

    st.download_button(
        label="Download Rapport 📄", 
        data=st.session_state.generated_report, 
        file_name=f"Financieel_Advies_{st.session_state.data.get('klant_referentie', 'User')}.md"
        )
        
        # Informatie en Reset buttons
    st.divider()
    st.info(f"Dit rapport is gebaseerd op de situatie van {st.session_state.data.get('klant_referentie', 'de gebruiker')}")

    with st.expander("Bekijk het schone dossier dat naar de AI is gestuurd"):
        st.text(generate_clean_dossier(st.session_state.data))

    if st.button("Nieuwe berekening maken 🔄", key="reset_app"):
        keys_to_delete = ['generated_report', 'ai_thread_started', 'ai_error', 'generating']
        for key in keys_to_delete:
            if key in st.session_state:
                del st.session_state[key]
        st.session_state.finished = False
        st.session_state.step = 1
        st.rerun()

# --- Loading (Test Genereren Scherm) ---
elif st.session_state.get('test_generating'):
    st.header("⏳ Test-Rapport wordt gegenereerd...")
    st.info("De AI analyseert nu het handmatig ingevoerde dossier. Dit duurt ongeveer 1 tot 2 minuten. Een moment geduld alsjeblieft!")
    
    schoon_dossier = st.session_state.test_dossier_input
    finance_crew = FinanceCrew()
    inputs = {'user_input': schoon_dossier}

    def run_test_ai_analysis(inputs_dict):
        try:
            result = finance_crew.crew().kickoff(inputs=inputs_dict)
            st.session_state.test_generated_report = result.raw
            
            expert_outputs = {}
            for task_output in result.tasks_output:
                name = task_output.description.split('\n')[0][:30]
                expert_outputs[name] = task_output.raw
                
            st.session_state.test_expert_analyses = expert_outputs
    
        except Exception as e:
            st.session_state.test_ai_error = str(e)

    if 'test_ai_thread_started' not in st.session_state:
        report_thread = threading.Thread(target=run_test_ai_analysis, args=(inputs,))
        add_script_run_ctx(report_thread) 
        report_thread.start()
        st.session_state.test_ai_thread_started = True

    progress_placeholder = st.empty()
    progress_text = "De AI-Coaches analyseren het test-dossier..."
    start_time = time.time()
    
    while 'test_generated_report' not in st.session_state and 'test_ai_error' not in st.session_state:
        elapsed = int(time.time() - start_time)
        progress_val = min(elapsed / 90.0, 0.95)
        progress_placeholder.progress(progress_val, text=f"{progress_text} ({elapsed}s)")
        time.sleep(0.5)

    progress_placeholder.empty()
    
    if 'test_ai_error' in st.session_state:
        st.error(f"Er is iets misgegaan: {st.session_state.test_ai_error}")
        if 'test_ai_thread_started' in st.session_state:
            del st.session_state.test_ai_thread_started
        st.stop()
    
    st.session_state.test_generating = False
    st.session_state.test_finished = True
    st.rerun()

# --- Finished (Test Rapportage Scherm) ---
elif st.session_state.get('test_finished'):
    st.header("📊 [TEST] Jouw Persoonlijk Financieel Rapport")
    st.markdown("---")
    st.markdown(st.session_state.test_generated_report)
    
    if 'test_expert_analyses' in st.session_state:
        with st.expander("🕵️ Bekijk de gedetailleerde analyses per expert (TEST)"):
            expert_names = list(st.session_state.test_expert_analyses.keys())
            tabs = st.tabs(expert_names)
            for i, name in enumerate(expert_names):
                with tabs[i]:
                    st.markdown(st.session_state.test_expert_analyses[name])
    st.divider()
    col_reset, col_back = st.columns(2)
    with col_reset:
        if st.button("Nieuwe AI-Test maken 🔄", use_container_width=True):
            for key in ['test_generated_report', 'test_ai_thread_started', 'test_ai_error', 'test_generating', 'test_finished']:
                if key in st.session_state: del st.session_state[key]
            st.rerun()
    with col_back:
        if st.button("Terug naar Vragenlijst 📝", use_container_width=True):
            for key in ['test_generated_report', 'test_ai_thread_started', 'test_ai_error', 'test_generating', 'test_finished', 'ai_test_mode']:
                if key in st.session_state: del st.session_state[key]
            st.rerun()

# --- AI-Test Modus (Input Scherm) ---
elif st.session_state.get('ai_test_mode'):
    st.header("🧪 AI-Test Modus")
    st.info("Plak hieronder een pre-gegenereerd 'schoon dossier'. Hiermee kun je direct de AI-agenten aan het werk zetten zonder de vragenlijst in te vullen.")
    
    test_dossier = st.text_area("Plak je dossier data (Markdown/Text):", height=400, key="test_dossier_input")
    
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Terug naar Vragenlijst", use_container_width=True):
            st.session_state.ai_test_mode = False
            st.rerun()
    with col2:
        if st.button("RUN AI TEST ✨", use_container_width=True):
            if test_dossier.strip():
                st.session_state.test_generating = True
                st.rerun()
            else:
                st.error("Plak eerst een dossier in het tekstvak voordat je de test start.")

# --- Questionnaire Flow ---
else:
    st.write(f"**Stap {st.session_state.step} van 8**")
    progress_bar = st.progress(st.session_state.step / 8)
    # --- STAP 1: PERSOONLIJK & DOELEN ---
    if st.session_state.step == 1:
        st.header("Stap 1: Persoonlijk & Doelen")
        
        with st.container(border=True):
            st.subheader("👤 Persoonsgegevens")
            # Input Naam
            st.text_input("Naam / Referentie", 
                        value=st.session_state.data.get('klant_referentie', ''), 
                        placeholder="Uw naam", 
                        key="klant_referentie_widget")
            
            # Input Leeftijd - Fix: zorg dat value minimaal de min_value is
            leeftijd_val = st.session_state.data.get('leeftijd')
            st.number_input("Leeftijd",
                            min_value=18, 
                            max_value=110, 
                            value=leeftijd_val if leeftijd_val else None,
                            placeholder="Uw leeftijd",
                            key="leeftijd_widget")
            
            # Input Burgerlijke Staat
            staat_opties = ["Alleenstaand", "Gehuwd / Geregistreerd partnerschap", "Samenwonend"]
            bestaande_staat = st.session_state.data.get('burgerlijke_staat', "Alleenstaand")
            # Veiligheidscheck voor index
            staat_index = staat_opties.index(bestaande_staat) if bestaande_staat in staat_opties else 0
            
            staat = st.radio("Burgerlijke staat", staat_opties, index=staat_index, key="burgerlijke_staat_widget")
            
            # Input Fiscaal Partnerschap
            if staat == "Samenwonend":
                partner_opties = ["Nee", "Ja"]
                partner_val = st.session_state.data.get('fiscaal_partnerschap', "Nee")
                partner_index = partner_opties.index(partner_val) if partner_val in partner_opties else 0
                st.radio("Vormt U een fiscaal partnerschap?", partner_opties, index=partner_index, key="fiscaal_partnerschap_widget")
            
            # Input Kinderen
            kind_opties = ["Nee", "Ja"]
            kind_val = st.session_state.data.get('kinderen', "Nee")
            kind_index = kind_opties.index(kind_val) if kind_val in kind_opties else 0
            kind = st.radio("Heeft U kinderen?", kind_opties, index=kind_index, key="kinderen_widget")      
            
            # Input Aantal en Leeftijd
            if kind == "Ja":
                col1, col2 = st.columns(2)
                with col1:
                    st.number_input("Aantal kinderen", 
                                min_value=1, 
                                value=st.session_state.data.get('aantal_kinderen', 1), 
                                key="aantal_kinderen_widget")
                with col2:
                    # We halen de default waarde op. Als deze niet bestaat, gebruiken we een lege lijst.
                    default_keuzes = st.session_state.data.get('leeftijd_categorie', [])
                    
                    st.multiselect(
                        "Welke leeftijdscategorieën zijn aanwezig?",
                        options=["Baby/Peuter/Kleuter", "Basisschool", "Tiener", "Volwassen"],
                        default=default_keuzes,
                        key="leeftijd_categorie_widget" # Gebruik een unieke widget key
                    )

            st.divider()
            st.subheader("🎯 Doelen & Zorgen")
            # Input Doel & Zorg
            st.text_input("Belangrijkste financiële doel(en)", 
                        value=st.session_state.data.get('belangrijkste_doel', ''), 
                        placeholder="Bijv. Eerder stoppen met werken", 
                        key="belangrijkste_doel_widget")
            
            st.text_input("Grootste financiële zorg", 
                        value=st.session_state.data.get('grootste_zorg', ''), 
                        placeholder="Bijv. Hoge maandlasten", 
                        key="grootste_zorg_widget")

        # Volgende Pagina Button
        if st.button("Volgende ➡️", use_container_width=True):
            errors = []
            
            # Validatie
            if not st.session_state.klant_referentie_widget.strip():
                errors.append("Vul a.u.b. een naam of referentie in.")
            
            if not st.session_state.belangrijkste_doel_widget.strip():
                errors.append("Vul a.u.b. een financieel doel in.")

            if st.session_state.kinderen_widget == "Ja" and not st.session_state.leeftijd_categorie_widget:
                errors.append("Selecteer a.u.b. een leeftijdscategorie voor de kinderen.")

            if errors:
                for error in errors:
                    st.error(error)
            else:
                # Data Opslaan
                st.session_state.data['datum'] = datetime.now().strftime("%Y-%m-%d")
                st.session_state.data['klant_referentie'] = st.session_state.klant_referentie_widget
                st.session_state.data['leeftijd'] = st.session_state.leeftijd_widget
                st.session_state.data['burgerlijke_staat'] = st.session_state.burgerlijke_staat_widget
                
                # Logica Partnerschap (Belastingdienst regels)
                if st.session_state.burgerlijke_staat_widget == "Gehuwd / Geregistreerd partnerschap":
                    st.session_state.data['fiscaal_partnerschap'] = "Ja"
                elif st.session_state.burgerlijke_staat_widget == "Samenwonend":
                    st.session_state.data['fiscaal_partnerschap'] = st.session_state.fiscaal_partnerschap_widget
                else:
                    st.session_state.data['fiscaal_partnerschap'] = "Nee"
                
                # Kinderen opschonen
                if st.session_state.kinderen_widget == "Ja":
                    st.session_state.data['kinderen'] = "Ja"
                    st.session_state.data['aantal_kinderen'] = st.session_state.aantal_kinderen_widget
                    # Sla hier de lijst van de widget op in je data dictionary
                    st.session_state.data['leeftijd_categorie'] = st.session_state.leeftijd_categorie_widget
                else:
                    st.session_state.data['kinderen'] = "Nee"
                    st.session_state.data.pop('aantal_kinderen', None)
                    st.session_state.data.pop('leeftijd_categorie', None)

                st.session_state.data['belangrijkste_doel'] = st.session_state.belangrijkste_doel_widget
                st.session_state.data['grootste_zorg'] = st.session_state.grootste_zorg_widget
                
                # Functie om naar stap 2 te gaan
                st.session_state.step = 2
                st.rerun()

    # --- STAP 2: WERK & INKOMEN ---
    elif st.session_state.step == 2:
        st.header("Stap 2: Werk & Inkomen")
        
        with st.container(border=True):
            st.subheader("💰 Inkomen")
            st.write("**Wat zijn uw inkomstenbronnen?**")
            
            # We halen de lijst met bronnen op uit de data voor de persistentie
            huidige_bronnen = st.session_state.data.get('inkomensbronnen', [])
            gekozen_bronnen = []
            
            bronnen_opties = [
                "Loondienst", 
                "Zzp", 
                "Inkomsten uit B.V./N.V.", 
                "Uitkering (WW, WIA, Bijstand)",
                "Vermogen (Huur, Dividend)",
                "Pensioen", 
                "Alimentatie (Ontvangen)",
                "Overig"
            ]
            
            # Checkboxen verdelen over twee kolommen
            col1, col2 = st.columns(2)
            for i, optie in enumerate(bronnen_opties):
                target_col = col1 if i % 2 == 0 else col2
                
                # Controleer of deze optie eerder was aangevinkt
                is_checked = optie in huidige_bronnen
                
                # De checkbox zelf
                if target_col.checkbox(optie, value=is_checked, key=f"cb_{optie}"):
                    gekozen_bronnen.append(optie)
            
            st.info("Vink alles aan wat voor u van toepassing is.")
            st.divider()

            # --- VRAGEN PER BRON ---

            if "Loondienst" in gekozen_bronnen:
                st.subheader("Loondienst")
                st.number_input("Bruto maandsalaris (in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('bruto_maand', 0)),
                                step=50, format="%d", 
                                key="bruto_maand_widget")
                
                # Opties voor de radiobuttons
                options = ["Ja", "Nee"]
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    # Vakantiegeld
                    val_vak = st.session_state.data.get('vakantiegeld', "Ja")
                    idx_vak = options.index(val_vak) if val_vak in options else 0
                    st.radio("Vakantiegeld?", options, index=idx_vak, key="vakantiegeld_widget", horizontal=True)
                    
                with c2:
                    # 13e maand
                    val_13 = st.session_state.data.get('dertiende_maand', "Nee")
                    idx_13 = options.index(val_13) if val_13 in options else 1
                    st.radio("13e maand?", options, index=idx_13, key="dertiende_maand_widget", horizontal=True)

                with c3:
                    # Bonus / Winstuitkering
                    val_bonus = st.session_state.data.get('heeft_bonus', "Nee")
                    idx_bonus = options.index(val_bonus) if val_bonus in options else 1
                    st.radio("Bonus/Winstuitkering?", options, index=idx_bonus, key="heeft_bonus_widget", horizontal=True)

                # Conditioneel veld voor bonus bedrag
                if st.session_state.heeft_bonus_widget == "Ja":
                    st.number_input("Gemiddelde bonus per jaar (bruto in €)", 
                                    min_value=0, 
                                    value=int(st.session_state.data.get('bonus_bedrag', 0)),
                                    step=100, key="bonus_bedrag_widget")
                
                st.divider()

            if "Zzp" in gekozen_bronnen:
                st.subheader("Zzp / Eenmanszaak")
                st.number_input("Gemiddelde bruto jaarwinst (laatste 3 jaar, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('winst_3_jaar', 0)), 
                                step=50, format="%d", 
                                key="winst_3_jaar_widget")
                st.number_input("Totaal aan zakelijke reserves (in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('zakelijke_reserves', 0)), 
                                step=50, format="%d", 
                                key="zakelijke_reserves_widget")
                st.divider()

            if "Inkomsten uit B.V./N.V." in gekozen_bronnen:
                st.subheader("Inkomsten uit B.V./N.V.")
                st.number_input("DGA salaris (bruto per jaar, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('dga_salaris', 0)), 
                                step=50, format="%d", 
                                key="dga_salaris_widget")
                st.number_input("Bruto winst B.V. (vóór VpB, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('bruto_winst', 0)), 
                                step=50, format="%d", 
                                key="bruto_winst_widget")
                st.number_input("Uitgekeerd bruto dividend afgelopen jaar B.V. (in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('dividend', 0)), 
                                step=50, format="%d", 
                                key="dividend_widget")
                st.divider()

            if "Uitkering (WW, WIA, Bijstand)" in gekozen_bronnen:
                st.subheader("Uitkering")
                st.number_input("Maandelijkse uitkering (bruto, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('uitkering_bedrag', 0)), 
                                step=50, format="%d", 
                                key="uitkering_bedrag_widget")
                st.divider()

            if "Vermogen (Huur, Dividend)" in gekozen_bronnen:
                st.subheader("Vermogen & Verhuur")
                st.number_input("Maandelijkse inkomsten uit verhuur/dividend in box 3 (bruto, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('vermogen_inkomen', 0)),
                                step=50, format="%d",  
                                key="vermogen_inkomen_widget")
                st.divider()

            if "Pensioen" in gekozen_bronnen:
                st.subheader("Pensioen")
                st.number_input("Totaal pensioeninkomen incl. AOW (bruto p/m, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('pensioen_inkomen', 0)),
                                step=50, format="%d",  
                                key="pensioen_inkomen_widget")
                st.divider()

            if "Alimentatie (Ontvangen)" in gekozen_bronnen:
                st.subheader("Partneralimentatie (Ontvangen)")
                st.number_input("Ontvangen partneralimentatie (bruto p/m, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('alimentatie_inkomen', 0)),
                                step=50, format="%d",  
                                key="alimentatie_inkomen_widget")
                st.divider()

            if "Overig" in gekozen_bronnen:
                st.subheader("Overig")
                st.number_input("Overig inkomen (bruto p/m, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('overig_inkomen', 0)),
                                step=50, format="%d",  
                                key="overig_inkomen_widget")
                st.divider()

        # --- OVERIGE ZAKEN & TOESLAGEN ---
        

        with st.container(border=True):
            st.subheader("Aftrekposten & Toeslagen")
            # Betaalde Alimentatie (Aftrekpost)
            alim_betaal_opties = ["Nee", "Ja"]
            bestaande_alim = st.session_state.data.get('betaalt_alimentatie', "Nee")
            alim_betaal_index = alim_betaal_opties.index(bestaande_alim)
            
            alim_keuze = st.radio(
                "Betaalt u partneralimentatie aan een ex-partner?", 
                alim_betaal_opties, 
                index=alim_betaal_index, 
                key="betaalt_alimentatie_widget",
                horizontal=True
            )
            
            if alim_keuze == "Ja":
                st.number_input(
                    "Totaal bedrag per maand aan betaalde alimentatie (in €)", 
                    min_value=0, 
                    value=int(st.session_state.data.get('alimentatie_betaald_bedrag', 0)), 
                    step=50,
                    key="alimentatie_betaald_bedrag_widget"
                )
            

            aftrek_opties = ["Nee", "Ja"]
            bestaande_aftrek = st.session_state.data.get('aftrek', "Nee")
            aftrek_index = aftrek_opties.index(bestaande_aftrek)
            
            aftrek_keuze = st.radio(
                "Heef U andere Box 1 aftrekposten in de afgelopen 12 maanden? Denk aan giften, uitgaven voor specifieke zorgkosten of aftrekbare kosten van de eigen woning.",
                aftrek_opties, 
                index=aftrek_index, 
                key="aftrek_widget",
                horizontal=True
            )
            
            if aftrek_keuze == "Ja":
                st.number_input(
                    "Totaal bedrag aftrekposten Box 1 voor de afgelopen 12 maanden (in €)", 
                    min_value=0, 
                    value=int(st.session_state.data.get('aftrek_bedrag', 0)), 
                    step=50,
                    key="aftrek_bedrag_widget"
                )

            st.divider()

            # Toeslagen
            st.write("**Welke toeslagen ontvangt u op dit moment?**")
            st.multiselect(
                "Selecteer alle die van toepassing zijn.", 
                ["Zorgtoeslag", "Huurtoeslag", "Kindgebonden budget", "Kinderopvangtoeslag"],
                default=st.session_state.data.get('toeslagen', []),
                key="toeslagen_widget"
            )

        # --- NAVIGATIE ---
        col_prev, col_spacer, col_next = st.columns([2, 3, 2])
        
        with col_prev:
            if st.button("⬅️ Vorige", use_container_width=True):
                # We slaan de huidige status op voordat we teruggaan
                st.session_state.data['inkomensbronnen'] = gekozen_bronnen
                st.session_state.step = 1
                st.rerun()

        with col_next:
            if st.button("Volgende ➡️", use_container_width=True, key="next_2"):
                errors = []
                
                # Validatie: moet tenminste één bron kiezen
                if not gekozen_bronnen:
                    errors.append("Selecteer a.u.b. tenminste één inkomstenbron.")
                
                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    # 1. Sla de lijst met bronnen op
                    st.session_state.data['inkomensbronnen'] = gekozen_bronnen
                    
                    # 2. Sla specifieke bron-data op (en schoon oude data op)
                    # Loondienst
                    if "Loondienst" in gekozen_bronnen:
                        st.session_state.data['bruto_maand'] = st.session_state.bruto_maand_widget
                        st.session_state.data['vakantiegeld'] = st.session_state.vakantiegeld_widget
                        st.session_state.data['dertiende_maand'] = st.session_state.dertiende_maand_widget
                        st.session_state.data['heeft_bonus'] = st.session_state.heeft_bonus_widget
                        
                        if st.session_state.heeft_bonus_widget == "Ja":
                            st.session_state.data['bonus_bedrag'] = st.session_state.bonus_bedrag_widget
                        else:
                            st.session_state.data.pop('bonus_bedrag', None)
                    else:
                        # Alles opschonen als Loondienst niet meer geselecteerd is
                        for k in ['bruto_maand', 'vakantiegeld', 'dertiende_maand', 'heeft_bonus', 'bonus_bedrag']:
                            st.session_state.data.pop(k, None)

                    # Zzp
                    if "Zzp" in gekozen_bronnen:
                        st.session_state.data['winst_3_jaar'] = st.session_state.winst_3_jaar_widget
                        st.session_state.data['zakelijke_reserves'] = st.session_state.zakelijke_reserves_widget
                    else:
                        st.session_state.data.pop('winst_3_jaar', None)
                        st.session_state.data.pop('zakelijke_reserves', None)

                    # B.V.
                    if "Inkomsten uit B.V./N.V." in gekozen_bronnen:
                        st.session_state.data['dga_salaris'] = st.session_state.dga_salaris_widget
                        st.session_state.data['bruto_winst'] = st.session_state.bruto_winst_widget
                        st.session_state.data['dividend'] = st.session_state.dividend_widget
                    else:
                        st.session_state.data.pop('dga_salaris', None)
                        st.session_state.data.pop('bruto_winst', None)

                    # Overige inkomens
                    source_mapping = {
                        "Uitkering (WW, WIA, Bijstand)": ('uitkering_bedrag', 'uitkering_bedrag_widget'),
                        "Vermogen (Huur, Dividend)": ('vermogen_inkomen', 'vermogen_inkomen_widget'),
                        "Pensioen": ('pensioen_inkomen', 'pensioen_inkomen_widget'),
                        "Alimentatie (Ontvangen)": ('alimentatie_inkomen', 'alimentatie_inkomen_widget'),
                        "Overig": ('overig_inkomen', 'overig_inkomen_widget')
                    }

                    for label, (data_key, widget_key) in source_mapping.items():
                        if label in gekozen_bronnen:
                            st.session_state.data[data_key] = st.session_state[widget_key]
                        else:
                            st.session_state.data.pop(data_key, None)

                    # 3. Alimentatie (Betaald)
                    st.session_state.data['betaalt_alimentatie'] = st.session_state.betaalt_alimentatie_widget
                    if st.session_state.betaalt_alimentatie_widget == "Ja":
                        st.session_state.data['alimentatie_betaald_bedrag'] = st.session_state.alimentatie_betaald_bedrag_widget
                    else:
                        st.session_state.data.pop('alimentatie_betaald_bedrag', None)

                    # 3.5 aftrekposten box 1 
                    st.session_state.data['aftrek'] = st.session_state.aftrek_widget
                    if st.session_state.aftrek_widget == "Ja":
                        st.session_state.data['aftrek_bedrag'] = st.session_state.aftrek_bedrag_widget
                    else:
                        st.session_state.data.pop('aftrek_bedrag', None)
                    
                    # 4. Toeslagen
                    st.session_state.data['toeslagen'] = st.session_state.toeslagen_widget
                    
                    # Bepaal de volgende stap
                    if st.session_state.data.get('fiscaal_partnerschap') == "Ja":
                        st.session_state.step = 2.5
                    else:
                        st.session_state.step = 3
                    st.rerun()
    
    # --- STAP 2.5: WERK & INKOMEN FISCAAL PARTNER ---
    elif st.session_state.step == 2.5:
        st.header("Stap 2.5: Werk & Inkomen van Fiscaal Partner")
        
        with st.container(border=True):
            st.subheader("💰 Inkomen")
            st.write("**Wat zijn de inkomstenbronnen van uw fiscaal partner?**")
            
            # We halen de lijst met bronnen op uit de data voor de persistentie
            huidige_bronnen_fp = st.session_state.data.get('inkomensbronnen_fp', [])
            gekozen_bronnen_fp = []
            
            bronnen_opties = [
                "Loondienst", 
                "Zzp", 
                "Inkomsten uit B.V./N.V.", 
                "Uitkering (WW, WIA, Bijstand)",
                "Vermogen (Huur, Dividend)",
                "Pensioen", 
                "Alimentatie (Ontvangen)",
                "Overig"
            ]
            
            # Checkboxen verdelen over twee kolommen
            col1, col2 = st.columns(2)
            for i, optie in enumerate(bronnen_opties):
                target_col = col1 if i % 2 == 0 else col2
                
                # Controleer of deze optie eerder was aangevinkt
                is_checked = optie in huidige_bronnen_fp
                
                # KEY AANGEPAST naar cb_fp_ om overlap met stap 2 te voorkomen
                if target_col.checkbox(optie, value=is_checked, key=f"cb_fp_{optie}"):
                    gekozen_bronnen_fp.append(optie)
            
            st.info("Vink alles aan wat voor de partner van toepassing is.")
            st.divider()

            # --- VRAGEN PER BRON ---
            if "Loondienst" in gekozen_bronnen_fp:
                st.subheader("Loondienst")
                st.number_input("Bruto maandsalaris (in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('bruto_maand_fp', 0)),
                                step=50, format="%d", 
                                key="bruto_maand_widget_fp")
                
                # Opties voor de radiobuttons
                options = ["Ja", "Nee"]
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    # Vakantiegeld
                    val_vak = st.session_state.data.get('vakantiegeld_fp', "Ja")
                    idx_vak = options.index(val_vak) if val_vak in options else 0
                    st.radio("Vakantiegeld?", options, index=idx_vak, key="vakantiegeld_widget_fp", horizontal=True)
                    
                with c2:
                    # 13e maand
                    val_13 = st.session_state.data.get('dertiende_maand_fp', "Nee")
                    idx_13 = options.index(val_13) if val_13 in options else 1
                    st.radio("13e maand?", options, index=idx_13, key="dertiende_maand_widget_fp", horizontal=True)

                with c3:
                    # Bonus / Winstuitkering
                    val_bonus = st.session_state.data.get('heeft_bonus_fp', "Nee")
                    idx_bonus = options.index(val_bonus) if val_bonus in options else 1
                    st.radio("Bonus/Winstuitkering?", options, index=idx_bonus, key="heeft_bonus_widget_fp", horizontal=True)

                # Conditioneel veld voor bonus bedrag
                if st.session_state.heeft_bonus_widget_fp == "Ja":
                    st.number_input("Gemiddelde bonus per jaar (bruto in €)", 
                                    min_value=0, 
                                    value=int(st.session_state.data.get('bonus_bedrag_fp', 0)),
                                    step=100, key="bonus_bedrag_widget_fp")

            if "Zzp" in gekozen_bronnen_fp:
                st.subheader("Zzp / Eenmanszaak")
                st.number_input("Gemiddelde bruto jaarwinst partner (laatste 3 jaar, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('winst_3_jaar_fp', 0)), 
                                step=50, format="%d", 
                                key="winst_3_jaar_widget_fp")
                st.number_input("Totaal aan zakelijke reserves partner (in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('zakelijke_reserves_fp', 0)), 
                                step=50, format="%d", 
                                key="zakelijke_reserves_widget_fp")
                st.divider()

            if "Inkomsten uit B.V./N.V." in gekozen_bronnen_fp:
                st.subheader("Inkomsten uit B.V./N.V.")
                st.number_input("DGA salaris partner (bruto per jaar, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('dga_salaris_fp', 0)), 
                                step=50, format="%d", 
                                key="dga_salaris_widget_fp")
                st.number_input("Bruto winst B.V. partner (vóór VpB, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('bruto_winst_fp', 0)), 
                                step=50, format="%d", 
                                key="bruto_winst_widget_fp")
                st.number_input("Uitgekeerd bruto dividend afgelopen jaar B.V. partner (in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('dividend_fp', 0)), 
                                step=50, format="%d", 
                                key="dividend_widget_fp")
                st.divider()

            if "Uitkering (WW, WIA, Bijstand)" in gekozen_bronnen_fp:
                st.subheader("Uitkering")
                st.number_input("Maandelijkse uitkering partner (bruto, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('uitkering_bedrag_fp', 0)), 
                                step=50, format="%d", 
                                key="uitkering_bedrag_widget_fp")
                st.divider()

            if "Vermogen (Huur, Dividend)" in gekozen_bronnen_fp:
                st.subheader("Vermogen & Verhuur")
                st.number_input("Maandelijkse inkomsten partner uit verhuur/dividend (bruto, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('vermogen_inkomen_fp', 0)),
                                step=50, format="%d",   
                                key="vermogen_inkomen_widget_fp")
                st.divider()

            if "Pensioen" in gekozen_bronnen_fp:
                st.subheader("Pensioen")
                st.number_input("Totaal pensioeninkomen partner incl. AOW (bruto p/m, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('pensioen_inkomen_fp', 0)),
                                step=50, format="%d",   
                                key="pensioen_inkomen_widget_fp")
                st.divider()

            if "Alimentatie (Ontvangen)" in gekozen_bronnen_fp:
                st.subheader("Partneralimentatie (Ontvangen)")
                st.number_input("Ontvangen partneralimentatie partner (bruto p/m, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('alimentatie_inkomen_fp', 0)),
                                step=50, format="%d",   
                                key="alimentatie_inkomen_widget_fp")
                st.divider()

            if "Overig" in gekozen_bronnen_fp:
                st.subheader("Overig")
                st.number_input("Overig inkomen partner (bruto p/m, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('overig_inkomen_fp', 0)),
                                step=50, format="%d",   
                                key="overig_inkomen_widget_fp")
                st.divider()

        # --- OVERIGE ZAKEN & TOESLAGEN PARTNER ---
        st.subheader("Aftrekposten & Toeslagen Partner")
        with st.container(border=True):
            alim_betaal_opties = ["Nee", "Ja"]
            bestaande_alim = st.session_state.data.get('betaalt_alimentatie_fp', "Nee")
            alim_betaal_index = alim_betaal_opties.index(bestaande_alim)
            
            alim_keuze = st.radio(
                "Betaalt u partneralimentatie aan een ex-partner?",
                alim_betaal_opties, 
                index=alim_betaal_index, 
                key="betaalt_alimentatie_widget_fp",
                horizontal=True
            )
            
            if alim_keuze == "Ja":
                st.number_input(
                    "Bedrag per maand aan betaalde alimentatie partner (in €)", 
                    min_value=0, 
                    value=int(st.session_state.data.get('alimentatie_betaald_bedrag_fp', 0)), 
                    step=50,
                    key="alimentatie_betaald_bedrag_widget_fp"
                )
            
            aftrek_opties_fp = ["Nee", "Ja"]
            bestaande_aftrek_fp = st.session_state.data.get('aftrek_fp', "Nee")
            aftrek_index_fp = aftrek_opties_fp.index(bestaande_aftrek_fp)
            
            aftrek_keuze_fp = st.radio(
                "Heef uw fiscaal partner andere Box 1 aftrekposten in de afgelopen 12 maanden? Denk aan giften, uitgaven voor specifieke zorgkosten of aftrekbare kosten van de eigen woning.",
                aftrek_opties_fp, 
                index=aftrek_index_fp, 
                key="aftrek_widget_fp",
                horizontal=True
            )
            
            if aftrek_keuze_fp == "Ja":
                st.number_input_fp(
                    "Totaal bedrag aftrekposten Box 1 voor de afgelopen 12 maanden (in €)", 
                    min_value=0, 
                    value=int(st.session_state.data.get('aftrek_bedrag_fp', 0)), 
                    step=50,
                    key="aftrek_bedrag_widget_fp"
                )

            st.divider()

            st.write("**Welke toeslagen ontvangt de partner (indien apart)?**")
            st.multiselect(
                "Selecteer alle die van toepassing zijn voor de partner.", 
                ["Zorgtoeslag", "Huurtoeslag", "Kindgebonden budget", "Kinderopvangtoeslag"],
                default=st.session_state.data.get('toeslagen_fp', []),
                key="toeslagen_widget_fp"
            )

        # --- NAVIGATIE ---
        col_prev, col_spacer, col_next = st.columns([2, 3, 2])
        
        with col_prev:
            if st.button("⬅️ Vorige", use_container_width=True, key="prev_btn_fp"):
                st.session_state.data['inkomensbronnen_fp'] = gekozen_bronnen_fp
                st.session_state.step = 2 # Terug naar jouw eigen inkomsten
                st.rerun()

        with col_next:
            if st.button("Volgende ➡️", use_container_width=True, key="next_btn_fp"):
                if not gekozen_bronnen_fp:
                    st.error("Selecteer a.u.b. tenminste één inkomstenbron voor de partner.")
                else:
                    # 1. Sla bronnenlijst op
                    st.session_state.data['inkomensbronnen_fp'] = gekozen_bronnen_fp
                    
                    # 2. Opslaan (Verwijst nu naar _widget_fp!)
                    if "Loondienst" in gekozen_bronnen_fp:
                        st.session_state.data['bruto_maand_fp'] = st.session_state.bruto_maand_widget_fp
                        st.session_state.data['vakantiegeld_fp'] = st.session_state.vakantiegeld_widget_fp
                        st.session_state.data['dertiende_maand_fp'] = st.session_state.dertiende_maand_widget_fp
                        st.session_state.data['heeft_bonus_fp'] = st.session_state.heeft_bonus_widget_fp
                        
                        if st.session_state.heeft_bonus_widget_fp == "Ja":
                            st.session_state.data['bonus_bedrag_fp'] = st.session_state.bonus_bedrag_widget_fp
                        else:
                            st.session_state.data.pop('bonus_bedrag_fp', None)
                    else:
                        # Alles opschonen als Loondienst niet meer geselecteerd is
                        for k in ['bruto_maand_fp', 'vakantiegeld_fp', 'dertiende_maand_fp', 'heeft_bonus_fp', 'bonus_bedrag_fp']:
                            st.session_state.data.pop(k, None)

                    if "Zzp" in gekozen_bronnen_fp:
                        st.session_state.data['winst_3_jaar_fp'] = st.session_state.winst_3_jaar_widget_fp
                        st.session_state.data['zakelijke_reserves_fp'] = st.session_state.zakelijke_reserves_widget_fp
                    else:
                        st.session_state.data.pop('winst_3_jaar_fp', None)
                        st.session_state.data.pop('zakelijke_reserves_fp', None)

                    if "Inkomsten uit B.V./N.V." in gekozen_bronnen_fp:
                        st.session_state.data['dga_salaris_fp'] = st.session_state.dga_salaris_widget_fp
                        st.session_state.data['bruto_winst_fp'] = st.session_state.bruto_winst_widget_fp
                        st.session_state.data['dividend_fp'] = st.session_state.dividend_widget_fp
                    else:
                        st.session_state.data.pop('dga_salaris_fp', None)
                        st.session_state.data.pop('bruto_winst_fp', None)

                    # Overige inkomens mapping gecorrigeerd naar _fp
                    source_mapping_fp = {
                        "Uitkering (WW, WIA, Bijstand)": ('uitkering_bedrag_fp', 'uitkering_bedrag_widget_fp'),
                        "Vermogen (Huur, Dividend)": ('vermogen_inkomen_fp', 'vermogen_inkomen_widget_fp'),
                        "Pensioen": ('pensioen_inkomen_fp', 'pensioen_inkomen_widget_fp'),
                        "Alimentatie (Ontvangen)": ('alimentatie_inkomen_fp', 'alimentatie_inkomen_widget_fp'),
                        "Overig": ('overig_inkomen_fp', 'overig_inkomen_widget_fp')
                    }

                    for label, (data_key, widget_key) in source_mapping_fp.items():
                        if label in gekozen_bronnen_fp:
                            st.session_state.data[data_key] = st.session_state[widget_key]
                        else:
                            st.session_state.data.pop(data_key, None)

                    # Alimentatie (Betaald) partner
                    st.session_state.data['betaalt_alimentatie_fp'] = st.session_state.betaalt_alimentatie_widget_fp
                    if st.session_state.betaalt_alimentatie_widget_fp == "Ja":
                        st.session_state.data['alimentatie_betaald_bedrag_fp'] = st.session_state.alimentatie_betaald_bedrag_widget_fp
                    else:
                        st.session_state.data.pop('alimentatie_betaald_bedrag_fp', None)
                    
                    # 3.5 aftrekposten box 1 
                    st.session_state.data['aftrek_fp'] = st.session_state.aftrek_widget_fp
                    if st.session_state.aftrek_widget_fp == "Ja":
                        st.session_state.data['aftrek_bedrag_fp'] = st.session_state.aftrek_bedrag_widget_fp
                    else:
                        st.session_state.data.pop('aftrek_bedrag_fp', None)
                    
                    st.session_state.data['toeslagen_fp'] = st.session_state.toeslagen_widget_fp
                    
                    st.session_state.step = 3 # Naar woonsituatie
                    st.rerun()

# --- STAP 3: HUIDIGE WOONSITUATIE ---
    elif st.session_state.step == 3:
        st.header("Stap 3: Huidige Woonsituatie")
        
        with st.container(border=True):
            # 1. Basis Woonsituatie
            st.subheader("🏠 Woonsituatie")
            woon_opties = ["Huurwoning", "Koopwoning", "Inwonend"]
            current_woon = st.session_state.data.get('woonsituatie', "Huurwoning")
            woon_index = woon_opties.index(current_woon) if current_woon in woon_opties else 0
            
            woon = st.radio("Wat is uw huidige woonsituatie?", woon_opties, index=woon_index, key="woonsituatie_widget")
            
            st.divider()

            # --- OPTIE: HUURWONING ---
            if woon == "Huurwoning":
                c1, c2 = st.columns(2)
                with c1:
                    st.number_input("Kale huur per maand (in €)", 
                                    min_value=0, 
                                    value=int(st.session_state.data.get('huurprijs', 0)), 
                                    step=50, key="huurprijs_widget")
                with c2:
                    st.number_input("Servicekosten per maand (in €)", 
                                    min_value=0, 
                                    value=int(st.session_state.data.get('servicekosten', 0)), 
                                    step=10, key="servicekosten_widget")
                
                st.checkbox("Is dit een sociale huurwoning?", 
                            value=st.session_state.data.get('sociale_huur', False), 
                            key="sociale_huur_widget")

            # --- OPTIE: KOOPWONING (Dynamisch voor meerdere huizen) ---
            elif woon == "Koopwoning":
                st.number_input("Aantal koopwoningen in bezit", 
                                min_value=1, max_value=5, 
                                value=int(st.session_state.data.get('aantal_huizen', 1)), 
                                step=1, key="aantal_huizen_widget")
                
                aantal_huizen = st.session_state.aantal_huizen_widget
                
                # Haal eventuele bestaande huizendata op uit de sessie
                huizen_data = st.session_state.data.get('huizen_lijst', [{} for _ in range(aantal_huizen)])
                # Zorg dat de lijst lang genoeg is als het aantal is opgehoogd
                while len(huizen_data) < aantal_huizen:
                    huizen_data.append({})

                # Loop door elke woning heen
                for i in range(aantal_huizen):
                    st.markdown(f"#### 📍 Woning {i+1}")
                    h_data = huizen_data[i]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        type_opties = ["Appartement", "Tussenwoning", "Hoekwoning", "2-onder-1-kap", "Vrijstaand"]
                        current_type = h_data.get('type_woning', "Tussenwoning")
                        type_index = type_opties.index(current_type) if current_type in type_opties else 1
                        st.selectbox(f"Type woning (Huis {i+1})", type_opties, index=type_index, key=f"type_woning_{i}")
                        
                        st.number_input(f"WOZ-waarde (Huis {i+1} in €)", 
                                        min_value=0, 
                                        value=int(h_data.get('woz_waarde', 0)), 
                                        step=5000, key=f"woz_waarde_{i}")
                    with col2:
                        label_opties = ["A+ of hoger", "A", "B", "C", "D", "E", "F", "G", "Onbekend"]
                        current_label = h_data.get('energielabel', "C")
                        label_index = label_opties.index(current_label) if current_label in label_opties else 3
                        st.selectbox(f"Energielabel (Huis {i+1})", label_opties, index=label_index, key=f"energielabel_{i}")
                        
                        bouwjaar_opties = ["Voor 1945", "1945-1970", "1971-1990", "1991-2010", "Na 2010"]
                        current_bj = h_data.get('bouwjaar_periode', "1991-2010")
                        bj_index = bouwjaar_opties.index(current_bj) if current_bj in bouwjaar_opties else 3
                        st.selectbox(f"Bouwjaar periode (Huis {i+1})", bouwjaar_opties, index=bj_index, key=f"bouwjaar_{i}")

                    # Hypotheek details per woning
                    heeft_hypo = st.checkbox(f"Heeft u een hypotheek op woning {i+1}?", 
                                            value=h_data.get('heeft_hypotheek', False), 
                                            key=f"heeft_hypotheek_{i}")
                    
                    if heeft_hypo:
                        st.write(f"*Hypotheekspecificatie voor Woning {i+1}*")
                        
                        vorm_opties = ["Annuïtair", "Lineair", "Aflossingsvrij", "Bankspaar", "Overig"]
                        geselecteerde_vormen = st.multiselect(
                            f"Kies de hypotheekvorm(en) voor Woning {i+1}",
                            options=vorm_opties,
                            default=h_data.get('gekozen_vormen', []),
                            key=f"hypo_vormen_{i}"
                        )
                        
                        # Dynamische velden per gekozen hypotheekvorm
                        vormen_details = h_data.get('vormen_details', {})
                        actuele_details = {}
                        
                        for vorm in geselecteerde_vormen:
                            st.markdown(f"**↳ Vorm: {vorm}**")
                            v_data = vormen_details.get(vorm, {})
                            
                            c_v1, c_v2 = st.columns(2)
                            with c_v1:
                                r_schuld = st.number_input(f"Restschuld {vorm} (in €)", min_value=0, value=int(v_data.get('restschuld', 0)), step=1000, key=f"restschuld_{vorm}_{i}")
                                r_percentage = st.number_input(f"Rentepercentage {vorm} (%)", min_value=0.0, max_value=15.0, value=float(v_data.get('rente', 0.0)), step=0.1, format="%.2f", key=f"rente_{vorm}_{i}")
                            with c_v2:
                                r_vaste_periode = st.number_input(f"Rentevaste periode {vorm} (in jaren over)", min_value=0, max_value=30, value=int(v_data.get('rentevaste_periode', 0)), step=1, key=f"rentevaste_{vorm}_{i}")
                            
                            actuele_details[vorm] = {
                                "restschuld": r_schuld,
                                "rente": r_percentage,
                                "rentevaste_periode": r_vaste_periode
                            }
                        
                        # Algemene bruto maandlast voor de gehele woning (inclusief HRA vermelding)
                        st.number_input(f"Bruto maandlast totale hypotheek Huis {i+1} (Vóór hypotheekrenteaftrek, in €)", 
                                        min_value=0, 
                                        value=int(h_data.get('hypo_maandlast_bruto', 0)), 
                                        step=50, key=f"hypo_maandlast_bruto_{i}")

                    # VvE & Erfpacht per woning
                    col_a, col_b = st.columns(2)
                    with col_a:
                        erfpacht = st.checkbox(f"Is er sprake van erfpacht bij Huis {i+1}?", 
                                                value=h_data.get('heeft_erfpacht', False), 
                                                key=f"heeft_erfpacht_{i}")
                        if erfpacht:
                            st.number_input(f"Jaarlijkse erfpachtcanon Huis {i+1} (in €)", 
                                            min_value=0, 
                                            value=int(h_data.get('erfpacht_canon', 0)), 
                                            key=f"erfpacht_canon_{i}")
                    with col_b:
                        if st.session_state[f"type_woning_{i}"] == "Appartement":
                            st.number_input(f"Maandelijkse VvE bijdrage Huis {i+1} (in €)", 
                                            min_value=0, 
                                            value=int(h_data.get('vve_bijdrage', 0)), 
                                            key=f"vve_bijdrage_{i}")
                    st.markdown("---")

            # --- OPTIE: INWONEND ---
            elif woon == "Inwonend":
                st.write("**Inwonend**")
                st.number_input("Maandelijkse vergoeding / kostgeld (in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('kostgeld', 0)), 
                                step=50, key="kostgeld_widget")
                st.caption("Vul 0 in als u geen maandelijkse vergoeding betaalt.")

            # --- ENERGIE, WATER & GEMEENTE (NIET Inwonend) ---
            if woon != "Inwonend":
                st.subheader("⚡ Energie, Water & Belastingen")
                e_col1, e_col2 = st.columns(2)
                with e_col1:
                    st.number_input("Maandlast Energie (Gas/Elektriciteit) (in €)", 
                                    min_value=0, 
                                    value=int(st.session_state.data.get('energie_lasten', 0)), 
                                    key="energie_widget")
                    
                    # VERANDERD: Nu expliciet per kwartaal aangegeven
                    st.number_input("Gemeentelijke heffingen PER KWARTAAL (OZB/Afval/Riool, in €)", 
                                    min_value=0, 
                                    value=int(st.session_state.data.get('gemeente_lasten_kwartaal', 0)), 
                                    step=25, key="gemeente_kwartaal_widget")
                with e_col2:
                    st.number_input("Maandlast Water (in €)", 
                                    min_value=0, 
                                    value=int(st.session_state.data.get('water_lasten', 0)), 
                                    key="water_widget")

        # --- NAVIGATIE & OPSLAG LOGICA ---
        col_prev, col_spacer, col_next = st.columns([2, 3, 2])
        
        with col_prev:
            if st.button("⬅️ Vorige", use_container_width=True):
                if st.session_state.data.get('fiscaal_partnerschap') == "Ja":
                    st.session_state.step = 2.5
                else:
                    st.session_state.step = 2
                st.rerun()

        with col_next:
            if st.button("Volgende ➡️", use_container_width=True, key="next_3"):
                woon_keuze = st.session_state.woonsituatie_widget
                st.session_state.data['woonsituatie'] = woon_keuze
                
                # Altijd opschonen om oude data-vervuiling te voorkomen
                base_keys = ['huurprijs', 'servicekosten', 'sociale_huur', 'kostgeld', 'huizen_lijst', 'aantal_huizen', 'energie_lasten', 'water_lasten', 'gemeente_lasten_kwartaal']
                
                if woon_keuze == "Huurwoning":
                    st.session_state.data['huurprijs'] = st.session_state.huurprijs_widget
                    st.session_state.data['servicekosten'] = st.session_state.servicekosten_widget
                    st.session_state.data['sociale_huur'] = st.session_state.sociale_huur_widget
                    st.session_state.data['energie_lasten'] = st.session_state.energie_widget
                    st.session_state.data['water_lasten'] = st.session_state.water_widget
                    st.session_state.data['gemeente_lasten_kwartaal'] = st.session_state.gemeente_kwartaal_widget
                    
                    # Verwijder koopwoning en inwonend data
                    for k in ['huizen_lijst', 'aantal_huizen', 'kostgeld']:
                        st.session_state.data.pop(k, None)

                elif woon_keuze == "Koopwoning":
                    st.session_state.data['aantal_huizen'] = st.session_state.aantal_huizen_widget
                    st.session_state.data['energie_lasten'] = st.session_state.energie_widget
                    st.session_state.data['water_lasten'] = st.session_state.water_widget
                    st.session_state.data['gemeente_lasten_kwartaal'] = st.session_state.gemeente_kwartaal_widget
                    
                    geconverteerde_huizen = []
                    for i in range(st.session_state.aantal_huizen_widget):
                        huis_dict = {
                            "type_woning": st.session_state[f"type_woning_{i}"],
                            "woz_waarde": st.session_state[f"woz_waarde_{i}"],
                            "energielabel": st.session_state[f"energielabel_{i}"],
                            "bouwjaar_periode": st.session_state[f"bouwjaar_{i}"],
                            "heeft_hypotheek": st.session_state[f"heeft_hypotheek_{i}"],
                            "heeft_erfpacht": st.session_state[f"heeft_erfpacht_{i}"]
                        }
                        
                        if huis_dict["heeft_hypotheek"]:
                            huis_dict["gekozen_vormen"] = st.session_state[f"hypo_vormen_{i}"]
                            huis_dict["hypo_maandlast_bruto"] = st.session_state[f"hypo_maandlast_bruto_{i}"]
                            
                            vorm_details = {}
                            for vorm in huis_dict["gekozen_vormen"]:
                                vorm_details[vorm] = {
                                    "restschuld": st.session_state[f"restschuld_{vorm}_{i}"],
                                    "rente": st.session_state[f"rente_{vorm}_{i}"],
                                    "rentevaste_periode": st.session_state[f"rentevaste_{vorm}_{i}"]
                                }
                            huis_dict["vormen_details"] = vorm_details
                        
                        if huis_dict["heeft_erfpacht"]:
                            huis_dict["erfpacht_canon"] = st.session_state[f"erfpacht_canon_{i}"]
                            
                        if st.session_state[f"type_woning_{i}"] == "Appartement":
                            huis_dict["vve_bijdrage"] = st.session_state[f"vve_bijdrage_{i}"]
                            
                        geconverteerde_huizen.append(huis_dict)
                    
                    st.session_state.data['huizen_lijst'] = geconverteerde_huizen
                    
                    # Verwijder huur en inwonend data
                    for k in ['huurprijs', 'servicekosten', 'sociale_huur', 'kostgeld']:
                        st.session_state.data.pop(k, None)

                elif woon_keuze == "Inwonend":
                    st.session_state.data['kostgeld'] = st.session_state.kostgeld_widget
                    # Verwijder alle overige keys
                    for k in [x for x in base_keys if x != 'kostgeld']:
                        st.session_state.data.pop(k, None)

                st.session_state.step = 4
                st.rerun()

    # --- STAP 4: TOEKOMSTIGE WOONWENS ---
    elif st.session_state.step == 4:
        st.header("Stap 4: Toekomstige Woonwens")
        
        with st.container(border=True):
            st.write("Wilt u in de nabije toekomst een woning kopen of doorstromen?")
            
            # VERANDERD: Checkbox vervangen door Radio-knoppen met index-retentie
            woonwens_opties = ["Ja", "Nee"]
            
            # Converteer de Boolean uit de data (True/False) naar de juiste index voor de radiobutton
            oude_wens = st.session_state.data.get('koopwens', False)
            woonwens_index = 0 if oude_wens is True else 1
            
            st.radio(
                "Heeft u een actieve koopwens?", 
                woonwens_opties, 
                index=woonwens_index, 
                key="koopwens_widget", 
                horizontal=True
            )
            
            # Conditionele velden tonen als de radiobutton op "Ja" staat
            if st.session_state.koopwens_widget == "Ja":
                st.divider()
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # Wanneer kopen?
                    termijn_opties = ["Zo snel mogelijk", "Binnen 1 jaar", "1-3 jaar", "3-5 jaar", "5+ jaar"]
                    current_termijn = st.session_state.data.get('koop_termijn', "1-3 jaar")
                    termijn_index = termijn_opties.index(current_termijn) if current_termijn in termijn_opties else 2
                    
                    st.selectbox("Op welke termijn wilt u kopen?", 
                                termijn_opties, 
                                index=termijn_index,
                                key="koop_termijn_widget")

                    # Type woning (Cruciaal voor Kosten Koper berekening)
                    type_bouw = ["Bestaande bouw", "Nieuwbouw", "Nog onbekend"]
                    current_bouw = st.session_state.data.get('koop_bouwtype', "Bestaande bouw")
                    bouw_index = type_bouw.index(current_bouw) if current_bouw in type_bouw else 0
                    st.selectbox("Voorkeur type woning", type_bouw, index=bouw_index, key="koop_bouwtype_widget")

                with col2:
                    # Geschatte prijs
                    st.number_input("Geschatte koopprijs droomwoning (in €)", 
                                    min_value=0, 
                                    value=int(st.session_state.data.get('koop_prijs', 0)), 
                                    step=5000, key="koop_prijs_widget")

                    # Eigen geld inbreng
                    st.number_input("Hoeveel eigen geld wilt u inleggen? (in €)", 
                                    min_value=0, 
                                    value=int(st.session_state.data.get('koop_eigen_geld', 0)), 
                                    step=1000, key="koop_eigen_geld_widget")
                    st.caption("Denk aan kosten koper: notariskosten, overdrachtsbelasting, e.d.")

            else:
                st.info("Geen actieve koopwens? Geen probleem.")

        # --- Navigatie ---
        col_prev, col_spacer, col_next = st.columns([2, 3, 2])
        
        with col_prev:
            if st.button("⬅️ Vorige", use_container_width=True):
                st.session_state.step = 3
                st.rerun()
                
        with col_next:
            if st.button("Volgende ➡️", use_container_width=True, key="next_4"):
                # Sla de status op als een zuivere Boolean (True/False) voor je CrewAI logica
                heeft_wens = st.session_state.koopwens_widget == "Ja"
                st.session_state.data['koopwens'] = heeft_wens
                
                # Alleen extra data opslaan als de wens er echt is
                if heeft_wens:
                    st.session_state.data['koop_termijn'] = st.session_state.koop_termijn_widget
                    st.session_state.data['koop_prijs'] = st.session_state.koop_prijs_widget
                    st.session_state.data['koop_eigen_geld'] = st.session_state.koop_eigen_geld_widget
                    st.session_state.data['koop_bouwtype'] = st.session_state.koop_bouwtype_widget
                else:
                    # Opschonen als de wens op "Nee" staat
                    keys_to_remove = ['koop_termijn', 'koop_prijs', 'koop_eigen_geld', 'koop_bouwtype']
                    for k in keys_to_remove:
                        st.session_state.data.pop(k, None)
                
                # Naar de volgende stap (Vermogen/Schulden/Auto's)
                st.session_state.step = 5
                st.rerun()
    # --- STAP 5: BEZIT EN SCHULDEN ---
    elif st.session_state.step == 5:
        # Check of er een partner is vanuit de eerdere data
        heeft_partner = st.session_state.data.get('fiscaal_partnerschap') == "Ja"
        label_prefix = "Vul het gezamenlijk totale vermogen in. Voor fiscale partners geldt een dubbele vrijstelling." if heeft_partner else "Vul uw totale vermogen in."
        
        st.header("Stap 5: Vermogen en schulden")
        
        with st.container(border=True):
            # Basis Ja/Nee opties voor de radiobuttons
            ja_nee_options = ["Ja", "Nee"]

            # --- 1. BEZITTINGEN ---
            st.subheader("📈 Bezittingen (Box 3)")
            st.caption(f"{label_prefix}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.number_input("Vrij beschikbare buffer (Sparen, in €)", 
                                min_value=0, value=int(st.session_state.data.get('buffer', 0)), 
                                step=500, key="buffer_widget")
                st.number_input("Totaalwaarde beleggingen (in €)", 
                                min_value=0, value=int(st.session_state.data.get('beleggingen', 0)), 
                                step=500, key="beleggingen_widget")
            with col2:
                st.number_input("Overig vermogen (Crypto, goud, etc., in €)", 
                                min_value=0, value=int(st.session_state.data.get('overig_vermogen', 0)), 
                                step=100, key="overig_vermogen_widget")
                
                # VERANDERD: Van checkbox naar radiobutton
                oude_ervaring = st.session_state.data.get('ervaring_beleggen', False)
                ervaring_index = 0 if oude_ervaring is True else 1
                st.radio("Ervaring met beleggen?", ja_nee_options, index=ervaring_index, key="ervaring_beleggen_widget", horizontal=True)
            
            st.divider()

            # --- 2. SCHULDEN (STUDIESCHULD GESPLITST) ---
            st.subheader("📉 Schulden")
            
            # VERANDERD: Van checkbox naar radiobutton voor eigen studieschuld
            oude_studie = st.session_state.data.get('heeft_studie', False)
            studie_index = 0 if oude_studie is True else 1
            st.radio("Heeft u (zelf) een studieschuld bij DUO?", ja_nee_options, index=studie_index, key="heeft_studie_widget", horizontal=True)
            
            if st.session_state.heeft_studie_widget == "Ja":
                st.markdown("*Uw studieschuld details:*")
                c1, c2 = st.columns(2)
                with c1:
                    st.number_input("Uw restantbedrag studieschuld (in €)", min_value=0, value=int(st.session_state.data.get('studie_bedrag', 0)), key="studie_bedrag_widget")
                    st.number_input("Uw resterende looptijd (maanden)", min_value=0, value=st.session_state.data.get('studie_looptijd', 0), key="studie_looptijd_widget")
                with c2:
                    st.number_input("Uw huidige rente (%)", min_value=0.0, max_value=10.0, step=0.01, format="%.2f", value=float(st.session_state.data.get('studie_rente', 0.00)), key="studie_rente_widget")
                    st.radio("Uw stelsel", ["SF15 (Oud)", "SF35 (Nieuw)"], index=0 if "SF15" in st.session_state.data.get('studie_stelsel', "SF15") else 1, key="studie_stelsel_widget", horizontal=True)
                st.markdown("---")

            # Studieschuld Partner (Alleen tonen als partner == Ja)
            if heeft_partner:
                # VERANDERD: Van checkbox naar radiobutton voor partner studieschuld
                oude_studie_fp = st.session_state.data.get('heeft_studie_fp', False)
                studie_fp_index = 0 if oude_studie_fp is True else 1
                st.radio("Heeft uw fiscaal partner een studieschuld bij DUO?", ja_nee_options, index=studie_fp_index, key="heeft_studie_fp_widget", horizontal=True)
                
                if st.session_state.heeft_studie_fp_widget == "Ja":
                    st.markdown("*Studieschuld details van uw partner:*")
                    cf1, cf2 = st.columns(2)
                    with cf1:
                        st.number_input("Restantbedrag partner (in €)", min_value=0, value=int(st.session_state.data.get('studie_bedrag_fp', 0)), key="studie_bedrag_fp_widget")
                        st.number_input("Resterende looptijd partner (maanden)", min_value=0, value=st.session_state.data.get('studie_looptijd_fp', 0), key="studie_looptijd_fp_widget")
                    with cf2:
                        st.number_input("Huidige rente partner (%)", min_value=0.0, max_value=10.0, step=0.01, format="%.2f", value=float(st.session_state.data.get('studie_rente_fp', 0.00)), key="studie_rente_fp_widget")
                        st.radio("Stelsel partner", ["SF15 (Oud)", "SF35 (Nieuw)"], index=0 if "SF15" in st.session_state.data.get('studie_stelsel_fp', "SF15") else 1, key="studie_stelsel_fp_widget", horizontal=True)
                    st.markdown("---")

            # Consumptieve schulden
            # VERANDERD: Van checkbox naar radiobutton voor consumptieve schulden
            oude_consumptief = st.session_state.data.get('consumptief_schuld', False)
            consumptief_index = 0 if oude_consumptief is True else 1
            st.radio("Zijn er consumptieve schulden?", ja_nee_options, index=consumptief_index, key="consumptief_schuld_widget", horizontal=True)
            st.caption("Consumptieve schulden zijn leningen voor persoonlijke uitgaven, zoals een auto, creditcard of vakantie.")
            
            if st.session_state.consumptief_schuld_widget == "Ja":
                cl1, cl2 = st.columns(2)
                with cl1:
                    st.number_input("Totaalbedrag schulden (in €)", min_value=0, value=int(st.session_state.data.get('consumptief_bedrag', 0)), key="consumptief_bedrag_widget")
                    st.number_input("Totale maandelijkse aflossing (in €)", min_value=0, value=int(st.session_state.data.get('consumptief_maandlast', 0)), key="consumptief_maandlast_widget")
                with cl2:
                    st.number_input("Gemiddelde rente op deze schulden (%)", min_value=0.0, max_value=20.0, step=0.1, value=float(st.session_state.data.get('consumptief_rente', 0.00)), key="consumptief_rente_widget")

            # --- 3. BKR SECTIE (VEREENVOUDIGD) ---
            st.divider()
            st.subheader("🛡️ BKR Status")
            
            oude_bkr = st.session_state.data.get('bkr_achterstand', False)
            bkr_index = 0 if oude_bkr is True else 1
            
            st.radio("Is er op dit moment sprake van een ACTIEVE BKR-achterstand?", 
                    ja_nee_options, index=bkr_index, key="bkr_achterstand_widget", horizontal=True)

            # --- 4. AUTO'S & MOBILITEIT ---
            st.divider()
            st.subheader("🚗 Auto's & Mobiliteit")
            
            aantal_autos = st.number_input("Hoeveel auto's zijn er in het huishouden?", 
                                            min_value=0, max_value=3, 
                                            value=int(st.session_state.data.get('aantal_autos', 0)), 
                                            key="aantal_autos_widget")
            
            oude_auto_data = st.session_state.data.get('autos_lijst', [{}, {}, {}])
            while len(oude_auto_data) < aantal_autos:
                oude_auto_data.append({})
                
            for i in range(1, aantal_autos + 1):
                with st.expander(f"Details Auto {i}", expanded=True):
                    this_auto = oude_auto_data[i-1]
                    ca1, ca2 = st.columns(2)
                    
                    with ca1:
                        situatie_opties = ["Privé auto (eigendom)", "Private lease", "Zakelijke auto", "Zakelijke lease"]
                        current_s = this_auto.get('situatie', "Privé auto (eigendom)")
                        s_index = situatie_opties.index(current_s) if current_s in situatie_opties else 0
                        
                        situatie = st.selectbox(f"Wat is de situatie van auto {i}?", situatie_opties, index=s_index, key=f"auto_situatie_{i}")
                    with ca2:
                        st.number_input(f"Bouwjaar auto {i}", min_value=1950, max_value=2026, value=int(this_auto.get('bouwjaar', 2020)), key=f"auto_bouwjaar_{i}")

                    oude_elek = this_auto.get('is_elektrisch', "Nee")
                    elek_index = ja_nee_options.index(oude_elek) if oude_elek in ja_nee_options else 1
                    st.radio(f"Is auto {i} een volledig elektrisch voertuig?", ja_nee_options, index=elek_index, key=f"auto_elektrisch_{i}", horizontal=True)

                    if "lease" in situatie.lower():
                        l1, l2 = st.columns(2)
                        with l1:
                            st.number_input(f"Leasebedrag p/m auto {i} (in €)", min_value=0, value=int(this_auto.get('lease_bedrag', 0)), key=f"auto_lease_bedrag_{i}")
                        with l2:
                            st.radio(f"Contracthouder auto {i}", ["Ikzelf", "Partner", "Nee"], key=f"auto_lease_naam_{i}")
                    
                    elif "Privé auto" in situatie:
                        st.number_input(f"Geschatte dagwaarde auto {i} (in €)", min_value=0, value=int(this_auto.get('waarde_prive', 0)), key=f"auto_waarde_prive_{i}")

        # --- NAVIGATIE & OPSLAG LOGICA ---
        col_prev, col_spacer, col_next = st.columns([2, 3, 2])
        with col_prev:
            if st.button("⬅️ Vorige", use_container_width=True):
                st.session_state.step = 4
                st.rerun()
                
        with col_next:
            if st.button("Volgende ➡️", use_container_width=True, key="next_5"):
                # 1. Basis bezittingen opslaan
                st.session_state.data['buffer'] = st.session_state.buffer_widget
                st.session_state.data['beleggingen'] = st.session_state.beleggingen_widget
                st.session_state.data['overig_vermogen'] = st.session_state.overig_vermogen_widget
                
                # VERANDERD: Ervaring met beleggen opslaan als Boolean (True/False)
                st.session_state.data['ervaring_beleggen'] = st.session_state.ervaring_beleggen_widget == "Ja"
                
                # 2. BKR Status opslaan als Boolean (True/False)
                st.session_state.data['bkr_achterstand'] = st.session_state.bkr_achterstand_widget == "Ja"

                # 3. DUO Opschonen / Opslaan (Mappen van "Ja" naar Boolean)
                heeft_studie_bool = st.session_state.heeft_studie_widget == "Ja"
                st.session_state.data['heeft_studie'] = heeft_studie_bool
                if heeft_studie_bool:
                    st.session_state.data['studie_bedrag'] = st.session_state.studie_bedrag_widget
                    st.session_state.data['studie_stelsel'] = st.session_state.studie_stelsel_widget
                    st.session_state.data['studie_rente'] = st.session_state.studie_rente_widget
                    st.session_state.data['studie_looptijd'] = st.session_state.studie_looptijd_widget
                else:
                    for k in ['studie_bedrag', 'studie_stelsel', 'studie_rente', 'studie_looptijd']:
                        st.session_state.data.pop(k, None)

                # Partner studieschuld
                if heeft_partner:
                    heeft_studie_fp_bool = st.session_state.heeft_studie_fp_widget == "Ja"
                    st.session_state.data['heeft_studie_fp'] = heeft_studie_fp_bool
                    if heeft_studie_fp_bool:
                        st.session_state.data['studie_bedrag_fp'] = st.session_state.studie_bedrag_fp_widget
                        st.session_state.data['studie_stelsel_fp'] = st.session_state.studie_stelsel_fp_widget
                        st.session_state.data['studie_rente_fp'] = st.session_state.studie_rente_fp_widget
                        st.session_state.data['studie_looptijd_fp'] = st.session_state.studie_looptijd_fp_widget
                    else:
                        for k in ['studie_bedrag_fp', 'studie_stelsel_fp', 'studie_rente_fp', 'studie_looptijd_fp']:
                            st.session_state.data.pop(k, None)
                else:
                    for k in ['heeft_studie_fp', 'studie_bedrag_fp', 'studie_stelsel_fp', 'studie_rente_fp', 'studie_looptijd_fp']:
                        st.session_state.data.pop(k, None)

                # 4. Consumptief Opschonen / Opslaan
                heeft_consumptief_bool = st.session_state.consumptief_schuld_widget == "Ja"
                st.session_state.data['consumptief_schuld'] = heeft_consumptief_bool
                if heeft_consumptief_bool:
                    st.session_state.data['consumptief_bedrag'] = st.session_state.consumptief_bedrag_widget
                    st.session_state.data['consumptief_maandlast'] = st.session_state.consumptief_maandlast_widget
                    st.session_state.data['consumptief_rente'] = st.session_state.consumptief_rente_widget
                else:
                    for k in ['consumptief_bedrag', 'consumptief_maandlast', 'consumptief_rente']:
                        st.session_state.data.pop(k, None)

                # 5. Auto's Opschonen / Opslaan
                aantal = st.session_state.aantal_autos_widget
                st.session_state.data['aantal_autos'] = aantal
                st.session_state.data['heeft_auto'] = aantal > 0
                
                lijst_voor_ai = []
                for i in range(1, aantal + 1):
                    auto_dict = {
                        "situatie": st.session_state[f"auto_situatie_{i}"],
                        "bouwjaar": st.session_state[f"auto_bouwjaar_{i}"],
                        "is_elektrisch": st.session_state[f"auto_elektrisch_{i}"]
                    }
                    
                    if f"auto_lease_bedrag_{i}" in st.session_state:
                        auto_dict["lease_bedrag"] = st.session_state[f"auto_lease_bedrag_{i}"]
                        auto_dict["contracthouder"] = st.session_state[f"auto_lease_naam_{i}"]
                    
                    if f"auto_waarde_prive_{i}" in st.session_state:
                        auto_dict["waarde_prive"] = st.session_state[f"auto_waarde_prive_{i}"]
                    
                    lijst_voor_ai.append(auto_dict)
                
                st.session_state.data['autos_lijst'] = lijst_voor_ai

                st.session_state.step = 6
                st.rerun()

    # --- STAP 6: UITGAVEN, LIFESTYLE ---
    elif st.session_state.step == 6:
        st.header("Stap 6: Uitgaven & Lifestyle")
        
        # Context-check voor dynamische teksten
        heeft_partner = st.session_state.data.get('fiscaal_partnerschap') == "Ja"
        prefix = "Onze" if heeft_partner else "Mijn"
        ja_nee_options = ["Ja", "Nee"]

        with st.container(border=True):
            # --- SECTIE 1: VASTE LASTEN (Verzekeringen & Contracten) ---
            st.subheader("🛡️ Verzekeringen & Vaste Lasten")
            st.caption("Exclusief wonen, energie en autolease (deze zijn al bekend).")
            
            v_col1, v_col2 = st.columns(2)
            with v_col1:
                st.number_input("Zorgverzekering(en) (per maand, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('uitgave_zorg', 0)), 
                                step=10, key="uitgave_zorg_widget")
                

            with v_col2:
                st.number_input("Telecom (Mobiel, Internet & TV, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('uitgave_telecom', 0)), 
                                step=5, key="uitgave_telecom_widget")

            # VERANDERD: Multiselect voor overige verzekeringen met dynamische bedragen
            verzekering_opties = ["Inboedelverzekering", "Opstalverzekering", "Aansprakelijkheid (AVP)", "Autoverzekering (Privé)", "Reisverzekering", "Rechtsbijstand", "Overig"]
            st.multiselect(
                "Welke overige verzekeringen heeft u lopen?",
                options=verzekering_opties,
                default=st.session_state.data.get('gekozen_verzekeringen', []),
                key="gekozen_verzekeringen_widget"
            )
            
            # Genereer dynamisch invoervelden voor de geselecteerde verzekeringen
            verzekeringen_details = st.session_state.data.get('verzekeringen_details', {})
            actuele_verzekeringen = {}
            total_overig_verzekeringen = 0
            
            if st.session_state.gekozen_verzekeringen_widget:
                st.info("💡 Vul per geselecteerde verzekering de maandpremie in:")
                for verz in st.session_state.gekozen_verzekeringen_widget:
                    oud_bedrag = verzekeringen_details.get(verz, 0)
                    bedrag = st.number_input(f"Premie {verz} (p/m, in €)", min_value=0, value=int(oud_bedrag), step=5, key=f"premie_{verz}")
                    actuele_verzekeringen[verz] = bedrag
                    total_overig_verzekeringen += bedrag
            st.divider()

            # --- SECTIE 2: ABONNEMENTEN ---
            st.subheader("📺 Abonnementen")
            st.caption("Denk aan Netflix, Spotify, de sportschool (inclusief sportverenigingen), kranten of loterijen.")
            
            st.number_input(f"Totaalbedrag {prefix.lower()} abonnementen per maand (in €)", 
                            min_value=0, 
                            value=int(st.session_state.data.get('uitgave_abonnementen', 0)), 
                            step=5, key="uitgave_abonnementen_widget")

            st.divider()

            # --- SECTIE 3: VARIABELE LASTEN ---
            st.subheader("🛒 Variabele Lasten")
            vl_col1, vl_col2 = st.columns(2)
            with vl_col1:
                st.number_input(f"{prefix} boodschappen per maand in €", 
                                min_value=0, 
                                value=int(st.session_state.data.get('boodschappen', 0)), 
                                step=50, key="boodschappen_widget")
                
                st.number_input("Vervoer (Benzine privé-auto, OV, parkeren, per maand in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('vervoer', 0)), 
                                step=25, key="vervoer_widget")
                
            with vl_col2:
                st.number_input("Vakantie & Reizen (omgerekend per maand, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('vakantie', 0)), 
                                step=50, key="vakantie_widget")
                
                # VERANDERD: 'Sport' is hier weggehaald uit de tekst
                st.number_input("Vrije tijd & Hobby's (Uitgaan, kleding, terras, etc., per maand in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('vrije_tijd', 0)), 
                                step=25, key="vrije_tijd_widget")

            st.divider()

            # --- SECTIE 4: LIFESTYLE & LEKKEN ---
            st.subheader("💸 Lifestyle & 'Lekken'")
            # VERANDERD: Tekst aangepast om hobby-perspectief te nuanceren
            st.write("Waar gaat maandelijks geld heen waarvan u de grip soms verliest? *(Let op: dit hoeft niet erg te zijn als het uw bewuste passie/hobby is!)*")
            
            leak_col1, leak_col2 = st.columns([2, 1])
            with leak_col1:
                st.multiselect("Vermoedelijke oorzaken van financiële lekken:", 
                                ["Uiteten/Thuisbezorgd", "Ongebruikte abonnementen", "Impulsaankopen", "Kleine uitgaven onderweg", "Bewuste hobby/passie uitgaven", "Geen"],
                                default=st.session_state.data.get('lekken', []), key="lekken_widget")
            with leak_col2:
                st.number_input("Geschat lekbedrag (p/m, in €)", 
                                min_value=0, 
                                value=int(st.session_state.data.get('lekbedrag', 0)), 
                                step=10, key="lekbedrag_widget")
                
            st.text_area("Toelichting op uitgaven of bewuste lifestyle keuzes (optioneel)", 
                        value=st.session_state.data.get('overige_uitgaven_tekst', ''), 
                        key="overige_uitgaven_tekst_widget",
                        placeholder="Bijv: 'Ik geef maandelijks veel uit aan speciaalbier of antiek, maar dit is echt mijn hobby en vind ik niet erg.'")

        # --- NIEUW: Vraag over de eigen schatting van het maandelijks overschot ---
            st.divider()
            st.subheader("📊 Gevoel van Grip")
            over_opties = ["Ik hou geld over", "Ik speel quitte", "Ik kom maandelijks tekort", "Geen idee"]
            current_over = st.session_state.data.get('schatting_overschot_status', "Geen idee")
            over_idx = over_opties.index(current_over) if current_over in over_opties else 3
            
            st.radio("Wat denkt u zelf dat uw situatie onder de streep is elke maand?", over_opties, index=over_idx, key="schatting_overschot_status_widget", horizontal=True)
            
            if st.session_state.schatting_overschot_status_widget == "Ik hou geld over":
                st.number_input("Hoeveel schat u maandelijks over te houden? (in €)", 
                                min_value=0, value=int(st.session_state.data.get('schatting_overschot_bedrag', 0)), step=50, key="schatting_overschot_bedrag_widget")
            
            # NIEUW: Vraag naar de hoogte van het tekort indien van toepassing
            elif st.session_state.schatting_overschot_status_widget == "Ik kom maandelijks tekort":
                st.number_input("Hoeveel komt u maandelijks gemiddeld tekort? (in €)", 
                                min_value=0, value=int(st.session_state.data.get('schatting_tekort_bedrag', 0)), step=50, key="schatting_tekort_bedrag_widget")

            st.divider()

        # --- NAVIGATIE & OPSLAG ---
        col_prev, col_spacer, col_next = st.columns([2, 3, 2])
        
        with col_prev:
            if st.button("⬅️ Vorige", use_container_width=True):
                st.session_state.step = 5
                st.rerun()
                
        with col_next:
            if st.button("Volgende ➡️", use_container_width=True, key="next_6"):
                # Finale opslag in session_state.data
                st.session_state.data['uitgave_zorg'] = st.session_state.uitgave_zorg_widget
                st.session_state.data['uitgave_telecom'] = st.session_state.uitgave_telecom_widget
                st.session_state.data['uitgave_abonnementen'] = st.session_state.uitgave_abonnementen_widget
                st.session_state.data['boodschappen'] = st.session_state.boodschappen_widget
                st.session_state.data['vervoer'] = st.session_state.vervoer_widget
                st.session_state.data['vakantie'] = st.session_state.vakantie_widget
                st.session_state.data['vrije_tijd'] = st.session_state.vrije_tijd_widget
                st.session_state.data['lekken'] = st.session_state.lekken_widget
                st.session_state.data['lekbedrag'] = st.session_state.lekbedrag_widget
                st.session_state.data['overige_uitgaven_tekst'] = st.session_state.overige_uitgaven_tekst_widget
                
                # Opslag Verzekeringen
                st.session_state.data['gekozen_verzekeringen'] = st.session_state.gekozen_verzekeringen_widget
                st.session_state.data['verzekeringen_details'] = actuele_verzekeringen
                st.session_state.data['uitgave_verzekeringen_overig'] = total_overig_verzekeringen
                
                # Opslag Grip/Overschot & Tekort logica
                st.session_state.data['schatting_overschot_status'] = st.session_state.schatting_overschot_status_widget
                if st.session_state.schatting_overschot_status_widget == "Ik hou geld over":
                    st.session_state.data['schatting_overschot_bedrag'] = st.session_state.schatting_overschot_bedrag_widget
                    st.session_state.data.pop('schatting_tekort_bedrag', None)
                elif st.session_state.schatting_overschot_status_widget == "Ik kom maandelijks tekort":
                    st.session_state.data['schatting_tekort_bedrag'] = st.session_state.schatting_tekort_bedrag_widget
                    st.session_state.data.pop('schatting_overschot_bedrag', None)
                else:
                    st.session_state.data.pop('schatting_overschot_bedrag', None)
                    st.session_state.data.pop('schatting_tekort_bedrag', None)

                st.session_state.step = 7
                st.rerun()

    # --- STAP 7: PENSIOEN & TOEKOMST ---
    elif st.session_state.step == 7:
        st.header("Stap 7: Pensioen & Toekomst")
        ja_nee_options = ["Ja", "Nee"]
        
        with st.container(border=True):
            st.subheader("🌅 Pensioen & Toekomst")
            p_col1, p_col2 = st.columns(2)
            with p_col1:
                oude_pw = st.session_state.data.get('pensioen_werkgever', True)
                pw_index = 0 if oude_pw is True else 1
                st.radio("Bouwt u momenteel pensioen op via een werkgever?", ja_nee_options, index=pw_index, key="pensioen_werkgever_widget", horizontal=True)
                st.caption("U kunt dit controleren op [mijnpensioenoverzicht.nl](https://www.mijnpensioenoverzicht.nl).")
                
                oude_lr = st.session_state.data.get('heeft_lijfrente', False)
                lr_index = 0 if oude_lr is True else 1
                st.radio("Heeft u een aanvullende lijfrente of pensioenspaarrekening?", ja_nee_options, index=lr_index, key="heeft_lijfrente_widget", horizontal=True)
                st.caption("Dit is een afgeschermde rekening bij een bank of verzekeraar (bijv. Brand New Day, Meesman, Bright).")
            
            with p_col2:
                st.number_input("Gewenste pensioenleeftijd", 
                                min_value=55, max_value=75, 
                                value=int(st.session_state.data.get('pensioenleeftijd', 67)), key="pensioenleeftijd_widget")

            if st.session_state.heeft_lijfrente_widget == "Ja":
                st.markdown("---")
                st.info("💡 **Aanvullende Lijfrente & Jaarruimte**\n\nAls zelfstandige of werknemer met een pensioentekort mag u fiscaal vriendelijk bijsparen. Uw **jaarruimte** en **reserveringsruimte** (ongebruikte ruimte van de afgelopen 10 jaar) bepalen hoeveel u maximaal mag aftrekken van de belasting.")
                
                cc1, cc2 = st.columns(2)
                with cc1:
                    st.number_input("Huidig totaal saldo op uw lijfrenterekening(en) (in €)", 
                                    min_value=0, 
                                    value=int(st.session_state.data.get('lijfrente_saldo', 0)), key="lijfrente_saldo_widget")
                with cc2:
                    jaar_opties = ["Ja, ik benut mijn jaarruimte", "Ja, ik benut ook mijn reserveringsruimte", "Nee, ik stort op gevoel", "Ik weet niet wat mijn ruimte is"]
                    jaar_val = st.session_state.data.get('jaarruimte_status', "Ik weet niet wat mijn ruimte is")
                    jaar_index = jaar_opties.index(jaar_val) if jaar_val in jaar_opties else 3
                    st.selectbox("Hoe benut u momenteel uw fiscale ruimte?", jaar_opties, index=jaar_index, key="jaarruimte_status_widget")
                    st.caption("U kunt uw exacte jaarruimte berekenen met de rekenhulp op de site van de Belastingdienst.")

        col_prev, col_spacer, col_next = st.columns([2, 3, 2])
        
        with col_prev:
            if st.button("⬅️ Vorige", use_container_width=True):
                st.session_state.step = 6
                st.rerun()
                
        with col_next:
            if st.button("Volgende ➡️", use_container_width=True, key="next_7"):
                st.session_state.data['pensioen_werkgever'] = st.session_state.pensioen_werkgever_widget == "Ja"
                st.session_state.data['pensioenleeftijd'] = st.session_state.pensioenleeftijd_widget
                
                heeft_lijfrente_bool = st.session_state.heeft_lijfrente_widget == "Ja"
                st.session_state.data['heeft_lijfrente'] = heeft_lijfrente_bool
                
                if heeft_lijfrente_bool:
                    st.session_state.data['lijfrente_saldo'] = st.session_state.lijfrente_saldo_widget
                    st.session_state.data['jaarruimte_status'] = st.session_state.jaarruimte_status_widget
                else:
                    st.session_state.data.pop('lijfrente_saldo', None)
                    st.session_state.data.pop('jaarruimte_status', None)

                # CrewAI trigger voorbereiden (Naar Stap 8: Controle)
                st.session_state.step = 8
                st.rerun()
    
# --- STAP 8: CONTROLE & BEVESTIGEN ---
    elif st.session_state.step == 8:
        st.header("🎯 Stap 8: Controleer je gegevens")
        st.info("Hieronder zie je een samenvatting van je invoer. Klopt alles? Klik dan onderaan op 'Genereer Rapport'.")

        # --- CATEGORIE 1: PERSOONLIJK & DOELEN ---
        # Gebaseerd op navigatie Deel 1
        with st.expander("👤 Persoonlijk & Doelen", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**Referentie:** {st.session_state.data.get('klant_referentie', 'Niet opgegeven')}")
                st.write(f"**Leeftijd:** {st.session_state.data.get('leeftijd', '-')} jaar")
                st.write(f"**Burgerlijke staat:** {st.session_state.data.get('burgerlijke_staat', '-')}")
                
                # Fiscaal partnerschap weergave
                fp = st.session_state.data.get('fiscaal_partnerschap', 'Nee')
                st.write(f"**Fiscaal partnerschap:** {'Ja' if fp == 'Ja' else 'Nee'}")
                
                # Kinderen logica
                if st.session_state.data.get('kinderen') == "Ja":
                    aantal = st.session_state.data.get('aantal_kinderen', '0')
                    cat = st.session_state.data.get('leeftijd_categorie', [])
                    cat_str = ", ".join(cat) if isinstance(cat, list) else str(cat)
                    st.write(f"**Kinderen:** {aantal} kind(eren) (Categorie: {cat_str})")
                else:
                    st.write("**Kinderen:** Nee")

            with c2:
                st.write(f"**Belangrijkste doel:** {st.session_state.data.get('belangrijkste_doel', '-')}")
                st.write(f"**Grootste zorg:** {st.session_state.data.get('grootste_zorg', '-')}")
                st.write(f"**Datum invoer:** {st.session_state.data.get('datum', '-')}")

        # --- CATEGORIE 2: WERK, INKOMEN & TOESLAGEN ---
        with st.expander("💰 Werk, Inkomen & Toeslagen", expanded=True):
            col_u, col_fp = st.columns(2)
            
            # --- LINKERKANT: GEBRUIKER ---
            with col_u:
                st.markdown("### **Uw Inkomen**")
                bronnen = st.session_state.data.get('inkomensbronnen', [])
                if not bronnen:
                    st.write("Geen inkomstenbronnen opgegeven.")
                
                if "Loondienst" in bronnen:
                    st.write(f"**Loondienst:** €{st.session_state.data.get('bruto_maand')}/mnd")
                    extra = []
                    if st.session_state.data.get('vakantiegeld') == "Ja": extra.append("Vakantiegeld")
                    if st.session_state.data.get('dertiende_maand') == "Ja": extra.append("13e maand")
                    if st.session_state.data.get('heeft_bonus') == "Ja": extra.append(f"Bonus : €{st.session_state.data.get('bonus_bedrag')}")
                    if extra: st.write(f"  *({', '.join(extra)})*")
                
                if "Zzp" in bronnen:
                    st.write(f"**ZZP Winst:** €{st.session_state.data.get('winst_3_jaar')}/jr (gem.)")
                    st.write(f"**Zakelijke reserves:** €{st.session_state.data.get('zakelijke_reserves')}")
                
                if "Inkomsten uit B.V./N.V." in bronnen:
                    st.write(f"**DGA Salaris:** €{st.session_state.data.get('dga_salaris')}/jr")
                    st.write(f"**Winst B.V.:** €{st.session_state.data.get('bruto_winst')}/jr")
                    st.write(f"**Dividend B.V.:** €{st.session_state.data.get('dividend')}/jr")
                
                # Mapping voor overige inkomsten
                overig_map = {
                    "Uitkering (WW, WIA, Bijstand)": ('uitkering_bedrag', 'Uitkering'),
                    "Vermogen (Huur, Dividend)": ('vermogen_inkomen', 'Vermogen'),
                    "Pensioen": ('pensioen_inkomen', 'Pensioen/AOW'),
                    "Alimentatie (Ontvangen)": ('alimentatie_inkomen', 'Alimentatie'),
                    "Overig": ('overig_inkomen', 'Overig')
                }
                for label, (key, display) in overig_map.items():
                    if label in bronnen:
                        st.write(f"**{display}:** €{st.session_state.data.get(key)}/mnd")

                st.write(f"**Toeslagen:** {', '.join(st.session_state.data.get('toeslagen', [])) or 'Geen'}")
                if st.session_state.data.get('betaalt_alimentatie') == "Ja":
                    st.write(f"**Betaalde alimentatie:** €{st.session_state.data.get('alimentatie_betaald_bedrag')}/mnd")
                if st.session_state.data.get('aftrek') == "Ja":
                    st.write(f"**Totaal Box 1 aftrek:** €{st.session_state.data.get('aftrek_bedrag')} in de afgelopen 12 maanden")

            # --- RECHTERKANT: PARTNER ---
            with col_fp:
                if fp == "Ja":
                    st.markdown("### **Inkomen Partner**")
                    bronnen_fp = st.session_state.data.get('inkomensbronnen_fp', [])
                    
                    if "Loondienst" in bronnen_fp:
                        st.write(f"**Loondienst:** €{st.session_state.data.get('bruto_maand_fp')}/mnd")
                        extra_fp = []
                        if st.session_state.data.get('vakantiegeld_fp') == "Ja": extra_fp.append("Vakantiegeld")
                        if st.session_state.data.get('dertiende_maand_fp') == "Ja": extra_fp.append("13e maand")
                        if st.session_state.data.get('heeft_bonus_fp') == "Ja": extra_fp.append(f"Bonus : €{st.session_state.data.get('bonus_bedrag_fp')}")
                        if extra_fp: st.write(f"  *({', '.join(extra_fp)})*")

                    if "Zzp" in bronnen_fp:
                        st.write(f"**ZZP Winst:** €{st.session_state.data.get('winst_3_jaar_fp')}/jr")
                        st.write(f"**Zakelijke reserves:** €{st.session_state.data.get('zakelijke_reserves_fp')}")

                    if "Inkomsten uit B.V./N.V." in bronnen_fp:
                        st.write(f"**DGA Salaris:** €{st.session_state.data.get('dga_salaris_fp')}/jr")
                        st.write(f"**Winst B.V.:** €{st.session_state.data.get('bruto_winst_fp')}/jr")
                        st.write(f"**Dividend B.V.:** €{st.session_state.data.get('dividend_fp')}/jr")

                    # Dezelfde mapping voor partner overig
                    overig_map_fp = {
                        "Uitkering (WW, WIA, Bijstand)": ('uitkering_bedrag_fp', 'Uitkering'),
                        "Vermogen (Huur, Dividend)": ('vermogen_inkomen_fp', 'Vermogen'),
                        "Pensioen": ('pensioen_inkomen_fp', 'Pensioen/AOW'),
                        "Alimentatie (Ontvangen)": ('alimentatie_inkomen_fp', 'Alimentatie'),
                        "Overig": ('overig_inkomen_fp', 'Overig')
                    }
                    for label, (key, display) in overig_map_fp.items():
                        if label in bronnen_fp:
                            st.write(f"**{display}:** €{st.session_state.data.get(key)}/mnd")

                    st.write(f"**Toeslagen Partner:** {', '.join(st.session_state.data.get('toeslagen_fp', [])) or 'Geen'}")
                    if st.session_state.data.get('betaalt_alimentatie_fp') == "Ja":
                        st.write(f"**Betaalde alimentatie:** €{st.session_state.data.get('alimentatie_betaald_bedrag_fp')}/mnd")
                    if st.session_state.data.get('aftrek_fp') == "Ja":
                        st.write(f"**Totaal Box 1 aftrek:** €{st.session_state.data.get('aftrek_bedrag_fp')} in de afgelopen 12 maanden")
                else:
                    st.write(" ") # Lege kolom voor layout balans
        # --- CATEGORIE 3: WONEN & WENSEN ---
        # Gecombineerd uit navigatie Stap 3 en Stap 4
        with st.expander("🏠 Wonen & Wensen", expanded=True):
            col_huidig, col_wens = st.columns(2)
            
            with col_huidig:
                st.markdown("### **Huidige Situatie**")
                woon = st.session_state.data.get('woonsituatie')
                st.write(f"**Woonsituatie:** {woon}")
                
                if woon == "Huurwoning":
                    st.write(f"**Kale huur:** €{st.session_state.data.get('huurprijs', 0)}/mnd")
                    st.write(f"**Servicekosten:** €{st.session_state.data.get('servicekosten', 0)}/mnd")
                    st.write(f"**Sociale huur:** {'Ja' if st.session_state.data.get('sociale_huur') else 'Nee'}")
                
                elif woon == "Koopwoning":
                    huizen = st.session_state.data.get('huizen_lijst', [])
                    st.write(f"**Aantal koopwoningen:** {st.session_state.data.get('aantal_huizen', 0)}")
                    for idx, huis in enumerate(huizen, 1):
                        st.markdown(f"**Woning {idx}**")
                        st.write(f"- Type: {huis.get('type_woning', '-')} | WOZ: €{huis.get('woz_waarde', 0)}")
                        st.write(f"- Energielabel: {huis.get('energielabel', '-')} | Bouwjaar: {huis.get('bouwjaar_periode', '-')}")
                        
                        if huis.get('heeft_hypotheek'):
                            st.write(f"- Hypotheek (bruto): €{huis.get('hypo_maandlast_bruto', 0)}/mnd")
                            vormen = huis.get('gekozen_vormen', [])
                            if vormen:
                                st.write(f"  *Vormen: {', '.join(vormen)}*")
                                for vorm in vormen:
                                    details = huis.get('vormen_details', {}).get(vorm, {})
                                    st.write(f"  * {vorm}: €{details.get('restschuld', 0)} ({details.get('rente', 0)}%, {details.get('rentevaste_periode', 0)} jr vast)")
                        
                        if huis.get('vve_bijdrage'):
                            st.write(f"- VvE bijdrage: €{huis.get('vve_bijdrage')}/mnd")
                        if huis.get('heeft_erfpacht'):
                            st.write(f"- Erfpachtcanon: €{huis.get('erfpacht_canon')}/jr")

                elif woon == "Inwonend":
                    st.write(f"**Kostgeld:** €{st.session_state.data.get('kostgeld', 0)}/mnd")

                # Energie & Belastingen (indien niet Inwonend)
                if woon != "Inwonend":
                    st.write(f"**G/W/L:** €{st.session_state.data.get('energie_lasten', 0) + st.session_state.data.get('water_lasten', 0)}/mnd")
                    st.write(f"**Gem. Belastingen:** €{st.session_state.data.get('gemeente_lasten_kwartaal', 0)}/kwartaal")

            with col_wens:
                st.markdown("### **Toekomstige Woonwens**")
                if st.session_state.data.get('koopwens'):
                    st.write("**Actieve koopwens:** Ja")
                    st.write(f"**Termijn:** {st.session_state.data.get('koop_termijn', '-')}")
                    st.write(f"**Type:** {st.session_state.data.get('koop_bouwtype', '-')}")
                    st.write(f"**Geschatte prijs:** €{st.session_state.data.get('koop_prijs', 0)}")
                    st.write(f"**Eigen inleg:** €{st.session_state.data.get('koop_eigen_geld', 0)}")
                else:
                    st.write("**Actieve koopwens:** Nee")

        # --- CATEGORIE 5: VERMOGEN & SCHULDEN ---
        with st.expander("📉 Vermogen & Schulden", expanded=True):
            col_v1, col_v2 = st.columns(2)
            
            with col_v1:
                st.markdown("### **Bezittingen**")
                st.write(f"**Spaarbuffer:** €{st.session_state.data.get('buffer', 0)}")
                st.write(f"**Beleggingen:** €{st.session_state.data.get('beleggingen', 0)}")
                st.write(f"**Overig vermogen:** €{st.session_state.data.get('overig_vermogen', 0)}")
                st.write(f"**Ervaring met beleggen:** {'Ja' if st.session_state.data.get('ervaring_beleggen') else 'Nee'}")

            with col_v2:
                st.markdown("### **Schulden & BKR**")
                
                # Studieschuld
                if st.session_state.data.get('heeft_studie'):
                    st.write(f"**Studieschuld:** €{st.session_state.data.get('studie_bedrag', 0)}")
                    st.write(f"  *({st.session_state.data.get('studie_stelsel')} | {st.session_state.data.get('studie_rente')}% rente)*")
                else:
                    st.write("**Studieschuld:** Geen")
                # Studieschuld FP                    
                if st.session_state.data.get('heeft_studie_fp'):
                    st.write(f"**Studieschuld Partner:** €{st.session_state.data.get('studie_bedrag_fp', 0)}")
                    st.write(f"  *({st.session_state.data.get('studie_stelsel_fp')} | {st.session_state.data.get('studie_rente_fp')}% rente)*")

                # Consumptief
                if st.session_state.data.get('consumptief_schuld'):
                    st.write(f"**Leningen/Krediet:** €{st.session_state.data.get('consumptief_bedrag', 0)}")
                    st.write(f"  *(Maandlast: €{st.session_state.data.get('consumptief_maandlast', 0)} | Rente: {st.session_state.data.get('consumptief_rente')}% )*")
                
                # BKR Status
                st.write(f"**BKR Achterstand:** {'Ja' if st.session_state.data.get('bkr_achterstand') else 'Nee'}")

        # --- CATEGORIE 4: AUTO & MOBILITEIT ---
        with st.expander("🚗 Auto & Mobiliteit", expanded=True):
            aantal = st.session_state.data.get('aantal_autos', 0)
            if aantal > 0:
                st.write(f"**Totaal aantal voertuigen:** {aantal}")
                autos_lijst = st.session_state.data.get('autos_lijst', [])
                
                # We maken kleine kolommen voor de auto-kaarten
                for idx, auto in enumerate(autos_lijst, 1):
                    st.markdown(f"**Voertuig {idx}:**")
                    c1, c2, c3 = st.columns([2, 2, 2])
                    with c1:
                        st.write(f"Situatie: {auto.get('situatie')}")
                    with c2:
                        st.write(f"Bouwjaar: {auto.get('bouwjaar')}")
                    with c3:
                        if "lease" in auto.get('situatie', '').lower():
                            st.write(f"Lease: €{auto.get('lease_bedrag')}/mnd")
                        elif "waarde_prive" in auto:
                            st.write(f"Dagwaarde: €{auto.get('waarde_prive')}")
                    st.divider()
            else:
                st.write("Geen voertuigen opgegeven.")

        # --- CATEGORIE 6: UITGAVEN & LIFESTYLE ---
        # Gebaseerd op navigatie Stap 6
        with st.expander("📝 Uitgaven & Lifestyle", expanded=True):
            col_lasten, col_lek = st.columns(2)
            
            with col_lasten:
                st.markdown("### **Maandelijkse Uitgaven**")
                st.write(f"**Zorgverzekering:** €{st.session_state.data.get('uitgave_zorg', 0)}/mnd")
                st.write(f"**Overige Verzekeringen:** €{st.session_state.data.get('uitgave_verzekeringen_overig', 0)}/mnd")
                st.write(f"**Telecom:** €{st.session_state.data.get('uitgave_telecom', 0)}/mnd")
                st.write(f"**Abonnementen:** €{st.session_state.data.get('uitgave_abonnementen', 0)}/mnd")
                
                st.markdown("---")
                st.write(f"**Boodschappen:** €{st.session_state.data.get('boodschappen', 0)}/mnd")
                st.write(f"**Vervoer (Benzine/OV):** €{st.session_state.data.get('vervoer', 0)}/mnd")
                st.write(f"**Hobby & Vrije tijd:** €{st.session_state.data.get('vrije_tijd', 0)}/mnd")

            with col_lek:
                st.markdown("### **Grip & Lekken**")
                lek_bedrag = st.session_state.data.get('lekbedrag', 0)
                if lek_bedrag > 0:
                    st.write(f"**💸 Financieel lek:** €{lek_bedrag}/mnd")
                    st.write(f"*(Oorzaken: {', '.join(st.session_state.data.get('lekken', []))})*")
                else:
                    st.write("**Financieel lek:** Geen opgegeven")
                    
                st.markdown("---")
                grip_status = st.session_state.data.get('schatting_overschot_status', 'Geen idee')
                st.write(f"**Gevoel van Grip:** {grip_status}")
                if grip_status == "Ik hou geld over":
                    st.write(f"- Geschat overschot: €{st.session_state.data.get('schatting_overschot_bedrag', 0)}/mnd")
                elif grip_status == "Ik kom maandelijks tekort":
                    st.write(f"- Geschat tekort: €{st.session_state.data.get('schatting_tekort_bedrag', 0)}/mnd")

                if st.session_state.data.get('overige_uitgaven_tekst'):
                    st.markdown("---")
                    st.markdown("**Extra toelichting:**")
                    st.info(st.session_state.data.get('overige_uitgaven_tekst'))

        # --- CATEGORIE 7: PENSIOEN & TOEKOMST ---
        with st.expander("🌅 Pensioen & Toekomst", expanded=True):
            st.write(f"**Pensioenleeftijd:** {st.session_state.data.get('pensioenleeftijd')} jaar")
            st.write(f"**Opbouw via werkgever:** {'Ja' if st.session_state.data.get('pensioen_werkgever') else '❌ Nee'}")
            
            if st.session_state.data.get('heeft_lijfrente'):
                st.write(f"**Aanvullende lijfrente:** Ja")
                st.write(f"- Huidig saldo: €{st.session_state.data.get('lijfrente_saldo', 0)}")
                st.write(f"- Jaarruimte benutting: {st.session_state.data.get('jaarruimte_status', 'Onbekend')}")
            else:
                st.write("**Aanvullende lijfrente:** Nee")

        # --- NAVIGATIE ONDERAAN ---
        st.divider()
        col_prev, col_debug, col_next = st.columns([1, 1, 1])
        
        with col_prev:
            if st.button("⬅️ Aanpassen", use_container_width=True, key="prev_btn_step_7"):
                st.session_state.step = 7
                st.rerun()
                
        with col_debug:
            if st.button("🔍 Test Dossier", use_container_width=True, key="test_dossier_btn"):
                st.session_state.show_debug = not st.session_state.get('show_debug', False)

        with col_next: 
            if st.button("GENEREER RAPPORT ✨", use_container_width=True, key="final_generate_btn"):
                st.session_state.generating = True
                st.rerun()

        # Debug Scherm
        if st.session_state.get('show_debug'):
            st.subheader("Voorbeeld van het Schone Dossier:")
            # Let op: zorg dat generate_clean_dossier gedefinieerd is in je code
            test_output = generate_clean_dossier(st.session_state.data)
            st.code(test_output, language="markdown")

    # --- AI-Test Navigatie (Onderaan elke pagina van de vragenlijst) ---
    st.markdown("<br>", unsafe_allow_html=True)
    st.divider()
    if st.button("🧪 AI-Test (Handmatig dossier uploaden)", use_container_width=True):
        st.session_state.ai_test_mode = True
        st.rerun()
