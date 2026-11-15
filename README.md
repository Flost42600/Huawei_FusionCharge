# Huawei FusionCharge pour Home Assistant

Intégration personnalisée qui pilote une borne Huawei SCharger (FusionCharge AC) **via le cloud FusionSolar**, sans OCPP ni EMMA.

- **Charge** : un interrupteur pour démarrer ou arrêter la charge (équivalent de « Charger maintenant »).
- **Charge programmée** : un interrupteur pour activer ou désactiver la programmation FusionSolar.
- **Mode de travail** : charge normale ou énergie verte (PV prioritaire).
- **Surveillance** : état de la connexion au cloud, de la borne et de la session Huawei, pour déclencher des alarmes.
- **Carte de tableau de bord** livrée avec l'intégration : la borne dessinée, son état, la puissance et les commandes.

Les plages horaires restent définies dans l'application FusionSolar. L'intégration ne les modifie jamais : elle les relit et les renvoie à l'identique quand elle active ou désactive la programmation.

> **Expérimental.** Les adresses utilisées ne sont pas documentées par Huawei : elles ont été relevées dans l'application FusionSolar par la communauté et peuvent changer sans préavis. Les commandes sont **désactivées par défaut**.

## Compatibilité

| Élément | État |
| --- | --- |
| Borne | SmartCharger-7KS-S0, logiciel FusionCharge V100R023C10SPC231 (validé : lecture, programmation, arrêt de charge) |
| Autres SCharger | SCharger-22KT-S0 testé par la communauté (fork Matthias2703 de FusionSolarPlus) |
| EMMA | Non nécessaire |
| Home Assistant | 2025.1 ou plus récent |

## Installation

**Avec HACS (recommandé) :** HACS > menu ⋮ > Dépôts personnalisés > URL du dépôt GitHub, type « Intégration ». Installez « Huawei FusionCharge », puis redémarrez Home Assistant.

**À la main :** copiez le dossier `huawei_fusioncharge` dans `config/custom_components/`, puis redémarrez Home Assistant.

## Configuration

1. Paramètres > Appareils et services > Ajouter une intégration > **Huawei FusionCharge**.
2. Saisissez l'identifiant et le mot de passe de l'application FusionSolar.
3. Saisissez le **sous-domaine** : le début de l'adresse affichée par votre navigateur une fois connecté à FusionSolar (par exemple `uni004eu5`). Vous pouvez aussi coller l'adresse entière.
4. Si Huawei affiche un **code de sécurité**, l'image apparaît dans la fenêtre : recopiez-le. Il n'est jamais déchiffré automatiquement.
5. La borne est détectée automatiquement.

**Activer les commandes :** sur la carte de l'intégration, cliquez sur **Configurer** et cochez « Activer les commandes ».

**Session conservée.** La session FusionSolar est sauvegardée et réutilisée après un redémarrage de Home Assistant : pas de nouveau code tant que Huawei ne la ferme pas. Si Huawei redemande un code, l'entité « Reconnexion requise » passe à « oui » et Home Assistant propose de se reconnecter dans Paramètres.

## Carte de tableau de bord

La carte est chargée automatiquement avec l'intégration. Pour l'ajouter : modifiez un tableau de bord > Ajouter une carte > cherchez **Huawei FusionCharge**. En YAML :

```yaml
type: custom:huawei-fusioncharge-card
```

Elle affiche :
- la borne, avec un anneau lumineux dont la couleur suit l'état : vert en charge, bleu en attente, gris au repos, rouge hors ligne ;
- la puissance, l'énergie et la durée de la session ;
- les interrupteurs **Charge** et **Programmation** ;
- le **Mode de travail** à choisir d'un geste ;
- les plages programmées **en heure locale**, avec leur mode (soleil = énergie verte, éclair = normal) ;
- l'heure de la dernière communication avec le cloud.

Options : `title` (nom affiché) et `device_id` (si vous avez plusieurs bornes).

Si la carte n'apparaît pas dans la liste, videz le cache du navigateur. En dernier recours, ajoutez la ressource `/huawei_fusioncharge/huawei-fusioncharge-card.js` (type module) dans Paramètres > Tableaux de bord > ⋮ > Ressources.

## Entités

Noms pour une installation en français et une borne nommée « Borne garage ».

| Entité | Type | Rôle | Présente |
| --- | --- | --- | --- |
| Charge | interrupteur | Démarre (« Charger maintenant », même hors plage) ou arrête la charge. L'état suit la puissance réelle délivrée | commandes activées |
| Charge programmée | interrupteur | Active ou désactive la programmation | commandes activées |
| Mode de travail | sélecteur | Charge normale ou énergie verte | commandes activées |
| Armer la programmation | bouton | Bouton « Programmer » de l'application : la borne attend les plages | commandes activées |
| Cloud FusionSolar | capteur binaire (connectivité) | Home Assistant joint le cloud. **Jamais indisponible** : « déconnecté » est l'alarme | toujours |
| Borne en ligne | capteur binaire (connectivité) | La borne est connectée au cloud Huawei | toujours |
| Reconnexion requise | capteur binaire (problème) | Huawei redemande le mot de passe ou un code | toujours |
| Véhicule branché | capteur binaire (prise) | Déduit du code d'état de la borne | toujours |
| Dernière communication | horodatage | Dernière lecture réussie | toujours |
| État | capteur (énumération) | Au repos, Véhicule branché, En attente de la programmation, En charge, Charge à l'énergie verte, En attente d'énergie verte, Charge terminée, Défaut… | toujours |
| Puissance de charge, Courant, Énergie de la session, Durée de la session, Énergie totale | capteurs | Valeurs de la borne | toujours |
| Mode de travail actuel, Programmation active | capteurs | Réglages lus dans le cloud | toujours |
| Plages programmées | capteur (diagnostic) | Nombre de plages ; le détail est en attributs (heures **UTC**) | toujours |

**Comment se combinent les réglages.** Programmation activée : chaque plage applique son propre mode (normal ou vert), le mode de travail global est ignoré. Programmation désactivée : le mode global s'applique (« normale » = charge immédiate, « énergie verte » = surplus solaire).

**Interrupteur Charge.** Juste après une commande, il affiche l'état demandé pendant au plus 2 min 30, le temps que la voiture réagisse et que le cloud remonte la puissance. Passé ce délai, il revient à l'état réel. L'attribut `last_result` indique alors `not_confirmed`, par exemple si la voiture refuse la charge ou est débranchée.

## Alarmes de connexion

Le fichier [`examples/alarme_connexion.yaml`](examples/alarme_connexion.yaml) contient quatre automatisations prêtes à adapter :

| Alarme | Déclencheur |
| --- | --- |
| Cloud injoignable | « Cloud FusionSolar » déconnecté depuis 5 min |
| Reconnexion requise | Huawei redemande un code |
| Borne hors ligne | « Borne en ligne » déconnectée depuis 5 min |
| Données trop anciennes | Aucune lecture réussie depuis 15 min |

## Fiabilité et sécurité

- **Relecture automatique** : une erreur réseau ponctuelle est retentée une fois avant d'être signalée.
- **Vérification après écriture** : le mode de travail et la programmation sont relus après chaque commande. En cas d'échec, une erreur s'affiche au lieu de prétendre avoir réussi.
- **Plages protégées** : avant d'activer ou de désactiver la programmation, les plages sont lues deux fois, sauvegardées (`.storage/huawei_fusioncharge_plan_backup.*`, 10 dernières), renvoyées à l'identique, puis comparées. Si le cloud refuse ou si elles reviennent différentes, elles sont restaurées.
- **Aucune plage cochée** : la programmation ne peut pas être activée. L'intégration le dit clairement, sans rien envoyer.
- **Plages ponctuelles** : le cloud enregistre chaque « Charger maintenant » comme une courte plage ponctuelle, qui reste dans la liste une fois terminée. Une plage ponctuelle terminée est retirée quand la programmation est activée ou désactivée (elle figure dans la sauvegarde) ; une plage en cours est renvoyée telle quelle. Si le cloud la refuse, arrêtez d'abord la charge avec l'interrupteur « Charge ».
- **Puissance maximale jamais écrite** : chez un utilisateur, la baisser sous celle d'une plage a effacé toutes les plages.
- **Débit limité** : au moins 3 s entre deux commandes ; mise à jour toutes les 30 s (temps réel) et 60 s (réglages), modifiable.
- **Journaux et diagnostics** : mot de passe, cookies et jetons ne sont jamais journalisés ; les diagnostics masquent l'identifiant, le mot de passe, l'identifiant et le numéro de série de la borne.
- **Stockage** : le mot de passe et la session sont conservés dans `.storage` de Home Assistant, comme pour toute intégration cloud.

## Validation sur votre installation

Commandes activées, voiture branchée :

1. **Mode de travail** : passez d'« Énergie verte » à « Normale » puis revenez ; vérifiez dans l'application FusionSolar.
2. **Programmation** : désactivez puis réactivez « Charge programmée » ; vérifiez que les plages restent cochées et identiques dans l'application.
3. **Charge hors plage** (essentiel pour l'automatisation du soir) : programmation active, en dehors des plages, allumez « Charge ». La puissance monte-t-elle dans les 2 minutes ?
4. **Retour aux plages** : éteignez « Charge », appuyez sur « Armer la programmation ». Le lendemain, la plage solaire démarre-t-elle ?
5. **Borne en ligne** : vérifiez que l'entité est « connectée ». Si elle reste indisponible, envoyez l'attribut `raw_text` (voir Limitations).

## Automatisation Volvo

[`examples/automation_volvo.yaml`](examples/automation_volvo.yaml) :
- **à l'heure choisie** (22 h par défaut) : si la Volvo est branchée, que son SOC est connu, récent et sous le seuil, que le cloud répond et qu'aucune charge n'est en cours, allume « Charge » ;
- **à la cible ou au débranchement** : éteint « Charge » et réarme la programmation pour rendre la main aux plages solaires.

Un SOC indisponible n'est jamais lu comme 0 %. Remplacez les entités `volvo_*` par celles de votre intégration Volvo.

## Limitations connues

- Une seule prise par borne (connecteur 1).
- « Borne en ligne » lit le signal 19999 quand la borne le fournit, sinon l'état de l'équipement dans l'arborescence FusionSolar. Ces valeurs ne sont pas documentées par Huawei ; les valeurs brutes sont en attributs.
- Les codes d'état suivent le registre Modbus 31006 documenté par la bibliothèque huawei-solar ; le code 2 (« En attente de la programmation ») a été vérifié sur une SmartCharger-7KS-S0.
- Les heures des plages sont stockées en UTC par le cloud ; la carte les convertit en heure locale.
- L'ordre des jours dans `repeat_period` n'est pas documenté : la carte affiche le nombre de jours, pas leurs noms.

## Tests

```bash
pip install pytest-homeassistant-custom-component
pytest
```

## Crédits et licence

Connexion FusionSolar reprise de [FusionSolarPlus](https://github.com/JortvanSchijndel/FusionSolarPlus) (Jort van Schijndel). Commandes de la borne relevées par le [fork de Matthias2703](https://github.com/Matthias2703/FusionSolarPlus/tree/feature/charger-control). Licence GNU GPL v3.

Ce projet n'est ni affilié à Huawei ni soutenu par Huawei.
