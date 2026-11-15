# Huawei FusionCharge pour Home Assistant

Intégration personnalisée qui pilote une borne Huawei SCharger (FusionCharge AC) **via le cloud FusionSolar**, sans OCPP ni EMMA.

Elle fait volontairement peu de choses :

- **Démarrer et arrêter la charge** (équivalent du bouton « Charger maintenant » de l'application).
- **Activer ou désactiver la charge programmée** de FusionSolar.
- **Choisir le mode de travail** : charge normale ou énergie verte (PV prioritaire).
- Afficher l'état, la puissance et l'énergie de la borne.

Les plages horaires restent définies dans l'application FusionSolar. L'intégration ne les modifie jamais : elle les relit et les renvoie à l'identique quand elle active ou désactive la programmation.

> **Expérimental.** Les adresses utilisées par l'intégration ne sont pas documentées par Huawei. Elles ont été relevées dans l'application FusionSolar par la communauté et peuvent changer sans préavis. Les commandes sont **désactivées par défaut**.

## Compatibilité

| Élément | État |
| --- | --- |
| Borne visée | SmartCharger-7KS-S0, logiciel FusionCharge V100R023C10SPC231 |
| Commandes testées par la communauté | SCharger-22KT-S0 avec EMMA, même firmware (fork Matthias2703 de FusionSolarPlus) |
| Installation sans EMMA | Non testée : voir la procédure de validation ci-dessous |
| Home Assistant | 2025.1 ou plus récent |

## Installation

**Avec HACS :** HACS > menu ⋮ > Dépôts personnalisés > ajoutez l'URL du dépôt, catégorie « Intégration ». Installez « Huawei FusionCharge » puis redémarrez Home Assistant.

**À la main :** décompressez `huawei_fusioncharge.zip` dans le dossier `config/custom_components/huawei_fusioncharge/`, puis redémarrez Home Assistant.

## Configuration

1. Paramètres > Appareils et services > Ajouter une intégration > **Huawei FusionCharge**.
2. Saisissez l'identifiant et le mot de passe de l'application FusionSolar.
3. Saisissez le **sous-domaine** : connectez-vous à FusionSolar dans un navigateur et recopiez le début de l'adresse, par exemple `uni004eu5` dans `https://uni004eu5.fusionsolar.huawei.com/…`. Vous pouvez aussi coller l'adresse entière.
4. Si Huawei affiche un **code de sécurité** (captcha), l'image apparaît dans la fenêtre : recopiez les caractères. Le code n'est jamais déchiffré automatiquement.
5. La borne est détectée automatiquement.

**Activer les commandes :** sur la carte de l'intégration, cliquez sur **Configurer** et cochez « Activer les commandes ». L'intégration se recharge et les boutons, l'interrupteur et le sélecteur apparaissent.

**Si la session expire** et que Huawei redemande un code, Home Assistant affiche une demande de réauthentification dans Paramètres. Les commandes échouent avec un message explicite tant que vous ne vous êtes pas reconnecté.

## Entités

Les noms ci-dessous sont ceux d'une installation en français, pour une borne nommée « Borne garage ».

| Entité | Type | Rôle | Toujours présente |
| --- | --- | --- | --- |
| État | capteur | État de la borne tel qu'affiché par FusionSolar | oui |
| Puissance de charge | capteur (kW) | Puissance instantanée | oui |
| Courant | capteur (A) | Courant de sortie | oui |
| Énergie de la session | capteur (kWh) | Énergie de la session en cours | oui |
| Durée de la session | capteur | Durée de la session en cours | oui |
| Énergie totale | capteur (kWh) | Compteur total de la borne | oui |
| Mode de travail actuel | capteur | Charge normale ou énergie verte | oui |
| Programmation active | capteur binaire | Charge programmée activée dans FusionSolar | oui |
| État de connexion | capteur (diagnostic) | Connexion borne-cloud | oui |
| Plages programmées | capteur (diagnostic) | Nombre de plages ; le détail est en attributs (heures **UTC**) | oui |
| Démarrer la charge | bouton | « Charger maintenant », même hors plage | commandes activées |
| Arrêter la charge | bouton | Arrête la charge en cours | commandes activées |
| Armer la programmation | bouton | Bouton « Programmer » de l'application : la borne attend les plages | commandes activées |
| Charge programmée | interrupteur | Active ou désactive la programmation | commandes activées |
| Mode de travail | sélecteur | Charge normale ou énergie verte | commandes activées |

**Comment se combinent les réglages.** Quand la charge programmée est activée, chaque plage applique son propre mode (normal ou vert) et le mode de travail global est ignoré. Quand elle est désactivée, le mode de travail global s'applique : « charge normale » correspond à « charge immédiate » dans l'application, « énergie verte » au surplus solaire.

## Fonctionnement et sécurité

- **Vérification après écriture.** Le mode de travail et la programmation sont relus après chaque commande (trois lectures espacées de 3 secondes, puis une nouvelle tentative). En cas d'échec, la commande renvoie une erreur au lieu de prétendre avoir réussi.
- **Plages protégées.** Le cloud remplace la liste entière des plages à chaque écriture. Avant d'activer ou de désactiver la programmation, l'intégration lit les plages deux fois et refuse d'agir si les deux lectures diffèrent, si une plage est incomplète, ou s'il existe une plage ponctuelle (non répétée). Les plages sont sauvegardées dans `.storage/huawei_fusioncharge_plan_backup.*` (10 dernières), puis comparées champ par champ après l'écriture. Si elles ne reviennent pas à l'identique, l'intégration les restaure et le signale.
- **Puissance maximale jamais écrite.** Chez un utilisateur, baisser la puissance maximale sous celle d'une plage a effacé toutes les plages côté cloud.
- **Débit limité.** Au moins 3 secondes entre deux commandes ; mise à jour toutes les 30 s (temps réel) et 60 s (mode et programmation), réglables.
- **Démarrer et arrêter.** Ces boutons envoient la même requête que l'application. Une commande acceptée par le cloud ne garantit pas la charge : le véhicule doit être branché et autorisé à charger.
- **Journaux.** Le mot de passe, les cookies et le jeton de session ne sont jamais journalisés. Les diagnostics masquent l'identifiant, le mot de passe, l'identifiant de la borne et son numéro de série.
- **Mot de passe.** Il est conservé dans la configuration de Home Assistant, comme pour toute intégration cloud, pour pouvoir se reconnecter.

## Validation sur votre installation

À faire une fois, commandes activées, véhicule branché. Notez les résultats : ils déterminent si l'automatisation du soir peut s'appuyer sur « Démarrer la charge ».

1. **Mode de travail.** Passez de « Énergie verte » à « Charge normale », puis revenez. Vérifiez chaque fois dans l'application FusionSolar.
2. **Charge hors plage.** Programmation activée, en dehors de toute plage : appuyez sur « Démarrer la charge ». La puissance monte-t-elle dans les deux minutes ? L'interrupteur « Charge programmée » reste-t-il activé ?
3. **Retour à la programmation.** Appuyez sur « Arrêter la charge », puis sur « Armer la programmation ». Le lendemain, la plage solaire démarre-t-elle normalement ?
4. **Interrupteur de programmation.** Désactivez puis réactivez « Charge programmée ». Vérifiez dans l'application que les plages sont strictement identiques.
5. **OCPP.** Si un serveur OCPP est configuré sur la borne, refaites le test 2 avec et sans OCPP.

Si un test échoue, les diagnostics de l'intégration (menu ⋮ > Télécharger les diagnostics) donnent l'état lu et le résultat de la dernière commande, sans données personnelles.

## Automatisation Volvo

Le fichier [`examples/automation_volvo.yaml`](examples/automation_volvo.yaml) propose deux automatisations :

- **À l'heure choisie** (22 h par défaut) : si la Volvo est branchée, que son SOC est connu, récent (moins d'une heure) et inférieur au seuil, et qu'aucune charge n'est en cours, appuie sur « Démarrer la charge ».
- **Quand le SOC atteint la cible, ou si la voiture est débranchée** : arrête la charge et réarme la programmation pour rendre la main aux plages solaires.

Un SOC indisponible n'est jamais lu comme 0 %. Seuils et heure sont réglables avec des entrées Home Assistant. Remplacez les entités `volvo_*` par celles de votre intégration Volvo.

## Limitations connues

- Une seule prise par borne (connecteur 1), ce qui est le cas de la SCharger.
- Les heures des plages sont stockées en UTC par le cloud ; l'attribut du capteur « Plages programmées » les montre telles quelles.
- La signification exacte de `repeat_period` (masque des jours) et de `charge_mode` dans les plages n'est pas documentée par Huawei.
- Le compte « intl » de FusionSolar est pris en charge par le code mais n'a pas été testé.

## Tests

```bash
pip install pytest-homeassistant-custom-component
pytest tests
```

## Crédits et licence

La connexion à FusionSolar reprend le code de [FusionSolarPlus](https://github.com/JortvanSchijndel/FusionSolarPlus) (Jort van Schijndel). Les commandes de la borne ont été relevées par le [fork de Matthias2703](https://github.com/Matthias2703/FusionSolarPlus/tree/feature/charger-control). Licence GNU GPL v3, comme ces projets.

Ce projet n'est ni affilié à Huawei ni soutenu par Huawei.
