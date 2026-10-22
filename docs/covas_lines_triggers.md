# The 190 voice lines of the game: when they play and where to read it

Confidence: **A** trace and moment confirmed in the documentation, the logs or EDDI, **B** trace probable, moment still to be checked in the game, **C** no known trace, cannot be triggered from the game files, **K** only after a command.

Proof: `doc` = Frontier Journal Manual, `log` = the owner's journals, `EDDI` / `EDCP` = what that program uses, `hyp` = a hypothesis to check in the game.
The texts carry the corrections made by listening. The clips were not listened to when this table was made.

Total: A 28, B 61, C 95, K 6.

| No | Text | Group | When the game says it | Trace in the game | Confidence | Proof |
|---|---|---|---|---|---|---|
| 001 | Cargothold at maximum capacity. | Cargo | cargo hold full | Status.Cargo >= Loadout.CargoCapacity | B | hyp |
| 002 | out of bounds warning. | Zones | leaving the zone boundary | none | C | - |
| 003 | chassis integrity critical | Hull and canopy | hull critical | journal HullDamage.Health | B | hyp |
| 004 | Mission objective complete. | Missions and messages | mission objective done | journal MissionCompleted | B | hyp |
| 005 | Warning, corrosion. Damage resistance weakened. | Alien attacks | corrosion | none | C | - |
| 006 | unknown system disruption | Alien attacks | disruption of an unknown system | none | C | - |
| 007 | Warning, hyperspace conduit unstable. | Alien attacks | unstable hyperspace conduit | Flags.BeingInterdicted or hyperdiction: a jump to the same system (EDDI) | B | doc+EDDI+hyp |
| 008 | Ship ready for boarding. | Docking and ships | ship ready for boarding | none | C | - |
| 009 | Warning, impulse attack, trajectory disruption. | Alien attacks | impulse attack | none | C | - |
| 010 | module repaired | Repairs | AFMU repaired a module | journal AfmuRepairs (EDDI: ShipAfmuRepairedEvent) | B | EDDI+hyp |
| 011 | Warning, landing gear not deployed. | Ship switches | landing or docking with the landing gear up | Flags.LandingGearDown = 0 plus altitude (derived) | B | hyp |
| 012 | Fuel scoop disengaged. | Fuel | end of fuel scooping | Flags.ScoopingFuel 1 -> 0 (EDDI: ShipFuelScoopEvent) | A | doc+EDDI |
| 013 | Warning, mass lock attack. | Alien attacks | mass lock attack | none | C | - |
| 014 | Target Shields Online | Targets and combat | target's shields are back | none (ShipTargeted.ShieldHealth only after a scan) | C | - |
| 015 | Landing gear retracted. | Ship switches | landing gear retracted | Flags.LandingGearDown 1 -> 0 | A | doc+log |
| 016 | Fighter docking sequence initiated. | Fighter and mothership | start of fighter docking | journal DockFighter (EDDI: VesselDockedEvent) | B | EDDI+hyp |
| 017 | Warning, malfunction attack. | Alien attacks | malfunction after an attack | none | C | - |
| 018 | Target structure destroyed. Thermal cascade event detected. | Targets and combat | target destroyed by a thermal cascade | none | C | - |
| 019 | Boarding Commission granted. | Docking and ships | permission to board granted | none | C | - |
| 020 | call unsuccessful | Missions and messages | hail unsuccessful | none | C | - |
| 021 | Repair sequence failed. Unable to process. | Repairs | AFMU could not repair | journal AfmuRepairs (EDDI: ShipAfmuRepairedEvent) | B | EDDI+hyp |
| 022 | Warning, hazardous environment. | Environment (on foot) | hazardous environment | none | C | - |
| 023 | systems compromised. | Module failures | systems damaged | none | C | - |
| 024 | canopy integrity at 50% | Hull and canopy | cockpit canopy at 50% | none | C | - |
| 025 | Warning, Shield breach attack. | Alien attacks | shields breached | none | C | - |
| 026 | capping pressure alert. | Hull and canopy | cabin pressure drop | journal CockpitBreached (EDDI: no variables) | B | EDDI+hyp |
| 027 | Fuel replenished. | Fuel | fuel replenished | journal RefuelAll or RefuelPartial, or the end of scooping with more fuel (EDDI: ShipRefuelledEvent) | A | log+EDDI |
| 028 | full | Unclear | ? | ? | C | - |
| 029 | Drive assist on. | Ship switches | SRV drive assist on | Flags.SrvDriveAssist 0 -> 1 | A | doc+log |
| 030 | Warning, incoming hatch breaker limpets. | Alien attacks | hostile hatch breaker limpets | none | C | - |
| 031 | Mothership Shields offline. | Fighter and mothership | mothership's shields are down | none | C | - |
| 032 | engage | Command acknowledgement | order "engage" | none | K | - |
| 033 | trespass zone cleared | Zones | leaving the trespass zone | none | C | - |
| 034 | Boarding Commission denied. | Docking and ships | permission to board denied | none | C | - |
| 035 | cargo scoop deployed | Ship switches | cargo scoop deployed | Flags.CargoScoopDeployed 0 -> 1 | A | doc+log |
| 036 | Ship delivery complete. | Docking and ships | ship delivery complete | journal ShipyardNew or ShipRedeemed (EDDI: ShipDeliveredEvent) | B | EDDI+hyp |
| 037 | Shields online. | Ship switches | shields on | Flags.ShieldsUp 0 -> 1 (EDDI deliberately skips the journal ShieldState) | A | doc+EDDI |
| 038 | Warning, you have entered a trespass zone. | Zones | entering the trespass zone | none | C | - |
| 039 | Landing gear deployed. | Ship switches | landing gear deployed | Flags.LandingGearDown 0 -> 1 | A | doc+log |
| 040 | Self-destruct sequence disengaged. | Self-destruct | cancelled | none | C | - |
| 041 | module malfunction | Module failures | module damaged | none | C | - |
| 042 | Self-destruct in 20 seconds. | Self-destruct | 20 seconds | timer from journal SelfDestruct, the countdown lasts about 31 s; the moment is still to be measured | B | log+hyp |
| 043 | Diagnostic repair sequence initiated. | Repairs | start of diagnostics | none | C | - |
| 044 | Docking successful. Engines disengaged. | Docking and ships | docking successful | journal Docked or Flags.Docked 0 -> 1 | A | doc+log |
| 045 | Warning, Engine reboot. | Module failures | engines restarting | none | C | - |
| 046 | affirmative | Command acknowledgement | order acknowledged | none | K | - |
| 047 | Heat sink deployed. | Command acknowledgement | heat sink fired | none (only after a command) | K | - |
| 048 | Mothership, Resuming Formation | Fighter and mothership | mothership returns to formation | none | C | - |
| 049 | All are disconnected. | Multicrew | everyone disconnected | journal EndCrewSession (EDDI) | B | EDDI+hyp |
| 050 | Target destroyed. | Targets and combat | target destroyed | journal Bounty or FactionKillBond | B | hyp |
| 051 | main fuel tank drained | Fuel | main tank empty | Status.Fuel.FuelMain = 0 | B | hyp |
| 052 | hatch brake Olympic engaged. | Limpets and mining | hatch breaker limpet launched | journal LaunchDrone, field Type (EDDI: LimpetLaunchedEvent) | B | EDDI+hyp |
| 053 | Prospect Olympic engaged. | Limpets and mining | prospector limpet launched | journal LaunchDrone, field Type (EDDI: LimpetLaunchedEvent) | B | EDDI+hyp |
| 054 | One. | Self-destruct | countdown: one | timer from journal SelfDestruct, the countdown lasts about 31 s; the moment is still to be measured | B | log+hyp |
| 055 | its assembly complete. | Fighter and mothership | fighter rebuilt | journal FighterRebuilt (EDDI: FighterRebuiltEvent) | B | EDDI+hyp |
| 056 | Collect a limp it expired. | Limpets and mining | collector limpet expired | none | C | - |
| 057 | Unknown anomaly detected. | Anomalies, scans, navigation | unknown anomaly | journal Music, MusicTrack = Unknown_Encounter (from the list in the documentation) | B | doc+hyp |
| 058 | Target destroyed. | Targets and combat | target destroyed | journal Bounty | B | hyp |
| 059 | hatch breaker limp it avoided. | Limpets and mining | hatch breaker limpet avoided | none | C | - |
| 060 | Self-destruct sequence initiated. | Self-destruct | start of the sequence | journal SelfDestruct = start of the sequence (your log 2026-02-22: SelfDestruct 18:44:12, Died 18:44:43) | A | log+EDDI |
| 061 | Warning, frame shift drive reboot. | Module failures | FSD restarting | none | C | - |
| 062 | under attack. | Hull and canopy | attack on the ship | journal UnderAttack, field Target = You/Fighter/Mothership | A | log+EDDI |
| 063 | Warning, targeting disrupted. | Alien attacks | targeting disrupted | none | C | - |
| 064 | Warning, Frame Shift Drive operating beyond safety limits. | Module failures | FSD beyond its limits | none | C | - |
| 065 | Weapons Rearms | Repairs | weapons restocked | journal BuyAmmo (EDDI: ShipRestockedEvent) | B | EDDI+hyp |
| 066 | Warning, taking heat damage. | Heat | heat damage | journal HeatDamage (EDDI: HeatDamageEvent) | A | doc+log+EDDI |
| 067 | Fighter assembly initiated. | Fighter and mothership | start of rebuilding the fighter | none | C | - |
| 068 | self-destruct in five | Self-destruct | countdown: five | timer from journal SelfDestruct, the countdown lasts about 31 s; the moment is still to be measured | B | log+hyp |
| 069 | fighter holding position | Fighter and mothership | fighter holds position | none | C | - |
| 070 | Shields offline. | Ship switches | shields off | Flags.ShieldsUp 1 -> 0 (EDDI deliberately skips the journal ShieldState) | A | doc+EDDI |
| 071 | Warning, thermal signature amplified. | Alien attacks | thermal signature amplified | none | C | - |
| 072 | flight assist off | Ship switches | flight assist off | Flags.FlightAssistOff 0 -> 1 | A | doc+log |
| 073 | canopy critical | Hull and canopy | canopy critical | none | C | - |
| 074 | Warning, oxygen critical. | Environment (on foot) | oxygen critical | Flags2.LowOxygen or Status.Oxygen (EDDI: available, no event) | B | doc+EDDI+hyp |
| 075 | programming limpet drone | Limpets and mining | programming a limpet | none | C | - |
| 076 | scan detected | Anomalies, scans, navigation | scanned by another ship | journal Scanned | A | doc+log |
| 077 | Fighter destroyed. | Fighter and mothership | fighter destroyed | journal FighterDestroyed (EDDI: VesselDestroyedEvent) | A | EDDI |
| 078 | Mission failed. | Missions and messages | mission failed | journal MissionFailed | A | doc+log |
| 079 | telepresence crew member, disconnected. | Multicrew | telepresence crew member disconnected | journal CrewMemberQuits (EDDI) | B | EDDI+hyp |
| 080 | incoming message. | Missions and messages | incoming message | journal ReceiveText | A | doc+log |
| 081 | asteroid depleted. | Limpets and mining | asteroid depleted | journal ProspectedAsteroid (EDCoPilot: MiningScannedDepletedAsteroid) | B | EDCP+hyp |
| 082 | Warning, sensor disruption. | Alien attacks | sensor disruption | none | C | - |
| 083 | warning, temperature critical | Heat | temperature critical | journal HeatWarning, > 100% (EDDI: HeatWarningEvent) or Flags.Overheating | B | doc+EDDI+hyp |
| 084 | fight a retrieval sequence, initiated. | Fighter and mothership | start of fighter retrieval | journal DockFighter (EDDI: VesselDockedEvent) | B | EDDI+hyp |
| 085 | main fuel tank low | Fuel | low fuel | Flags.LowFuel false -> true, < 25% (EDDI: LowFuelEvent) | A | doc+EDDI |
| 086 | eject | Unclear | "eject" | ? | C | - |
| 087 | Target shields offline. | Targets and combat | target's shields are down | none | C | - |
| 088 | hull integrity critical | Hull and canopy | hull critical | journal HullDamage.Health | B | hyp |
| 089 | Warning, temperature critical. | Heat | temperature critical (variant) | journal HeatWarning, > 100% (EDDI: HeatWarningEvent) or Flags.Overheating | B | doc+EDDI+hyp |
| 090 | feel scooping | Fuel | start of fuel scooping | Flags.ScoopingFuel 0 -> 1 (EDDI: ShipFuelScoopEvent) | A | doc+EDDI |
| 091 | rotational correction enabled | Effects and modes | rotational correction on | none | C | - |
| 092 | chassis integrity compromised. | Hull and canopy | hull weakened | journal HullDamage.Health | B | hyp |
| 093 | Prospect Olympic, expired. | Limpets and mining | prospector limpet expired | none | C | - |
| 094 | Target structure destroyed, thermal spike detected. | Targets and combat | target destroyed by a thermal spike | none | C | - |
| 095 | ready to engage. | Unclear | ready to engage | none | C | - |
| 096 | System review sequence initiated. | Repairs | start of the systems review | none | C | - |
| 097 | incoming fuel. | Fuel | fuel coming from another ship | none | C | - |
| 098 | Warning, hull breach attack, taking internal damage. | Alien attacks | hull breach | none | C | - |
| 099 | Warning, target system safety risk. | Anomalies, scans, navigation | danger in the target system | system faction data (EDCoPilot: Wanted/Hostile/IllegalCargo/Warrant InSystem), moment uncertain | C | EDCP |
| 100 | Taking damage. | Hull and canopy | you are taking damage | journal HullDamage, fields PlayerPilot and Fighter (maybe a variant per target) | B | EDDI+hyp |
| 101 | Target cargo dropped. | Targets and combat | target dropped its cargo | none | C | - |
| 102 | thermal signature restored. | Heat | thermal signature back to normal | Flags.Overheating 1 -> 0 | B | hyp |
| 103 | transferring fuel. | Fuel | transferring fuel | none | C | - |
| 104 | Ship Race, Engines Engaged. | Effects and modes | start of a ship race | none | C | - |
| 105 | incoming mission critical message. | Missions and messages | important mission message | journal ReceiveText | B | hyp |
| 106 | self-destruct in 10 seconds. | Self-destruct | 10 seconds | timer from journal SelfDestruct, the countdown lasts about 31 s; the moment is still to be measured | B | log+hyp |
| 107 | Low gravity warning. | Environment (on foot) | low gravity | Status.Gravity on foot or journal ApproachBody with the body's gravity (EDCoPilot) | B | doc+EDCP+hyp |
| 108 | telepresence crew member, connected. | Multicrew | telepresence crew member joined | journal CrewMemberJoins (EDDI) | B | EDDI+hyp |
| 109 | incoming audio message. | Missions and messages | audio message | journal ReceiveText | B | hyp |
| 110 | High Gravity Warning | Environment (on foot) | high gravity | Status.Gravity on foot or journal ApproachBody with the body's gravity (EDCoPilot, 3 g threshold) | B | doc+EDCP+hyp |
| 111 | Mothership Hull, critical. | Fighter and mothership | mothership's hull critical | journal HullDamage: PlayerPilot = false, Fighter = true (EDDI) | B | EDDI+hyp |
| 112 | Fighter deployed | Fighter and mothership | fighter launched | journal LaunchFighter (EDDI: VesselLaunchedEvent) | A | EDDI |
| 113 | Docking request denied. | Docking and ships | docking denied | journal DockingDenied | A | doc+log |
| 114 | Fighter unable to dock. | Fighter and mothership | fighter cannot dock | none | C | - |
| 115 | Fighter deployment sequence initiated. | Fighter and mothership | start of launching the fighter | journal LaunchFighter (EDDI: VesselLaunchedEvent) | B | EDDI+hyp |
| 116 | Warning, module malfunction. | Module failures | module damaged (warning) | none | C | - |
| 117 | Mission objective detected. | Missions and messages | mission objective detected | none | C | - |
| 118 | power plant capacity exceeded. | Module failures | power plant capacity exceeded | none | C | - |
| 119 | Prospect to Limpet, failed. | Limpets and mining | prospector limpet failed | none | C | - |
| 120 | module transfer complete. | Docking and ships | module transfer complete | journal FetchRemoteModule plus timer (EDDI: ModuleArrivedEvent) | B | EDDI+hyp |
| 121 | Hull Integrity compromised. | Hull and canopy | hull weakened | journal HullDamage.Health | B | hyp |
| 122 | frameshift anomaly detected | Anomalies, scans, navigation | FSD jump anomaly | none | C | - |
| 123 | Two. | Self-destruct | countdown: two | timer from journal SelfDestruct, the countdown lasts about 31 s; the moment is still to be measured | B | log+hyp |
| 124 | docking request granted | Docking and ships | docking granted | journal DockingGranted | A | doc+log |
| 125 | Frame Shift Charge detected. | Anomalies, scans, navigation | another ship's FSD charging | none | C | - |
| 126 | driver assist off. | Ship switches | SRV drive assist off | Flags.SrvDriveAssist 1 -> 0 | A | doc+log |
| 127 | Unable to dock, fighters still deployed. | Fighter and mothership | cannot dock, fighters are outside | none | C | - |
| 128 | incoming hail | Missions and messages | hail | none | C | - |
| 129 | Warning, Shield Cell Attack. | Alien attacks | shield cell attack | none | C | - |
| 130 | Order received. | Command acknowledgement | order received | none | K | - |
| 131 | fighter requesting to dock. | Fighter and mothership | fighter asks to dock | none | C | - |
| 132 | stealth mode | Ship switches | stealth mode | Flags.SilentRunning | B | hyp |
| 133 | atmospheric failure. | Environment (on foot) | atmosphere failure | none | C | - |
| 134 | Ship transfer complete. | Docking and ships | ship transfer complete | journal ShipyardTransfer plus a timer from the transfer time (EDDI: ShipArrivedEvent) | B | EDDI+hyp |
| 135 | Limpet drone error. Deploy cargo hatch. | Limpets and mining | limpet with the cargo hatch closed | none | C | - |
| 136 | Warning, approaching telepresence range limit. | Multicrew | approaching the range limit | none | C | - |
| 137 | Rotation or correction disabled. | Effects and modes | rotational correction off | none | C | - |
| 138 | silent running | Ship switches | silent running | Flags.SilentRunning | B | hyp |
| 139 | Shield boost. | Effects and modes | shield boost | none | C | - |
| 140 | Telepresence disruption detected. | Multicrew | telepresence disruption | none | C | - |
| 141 | No cargo detected. | Limpets and mining | no cargo | none | C | - |
| 142 | Warning, engine disruption. Drives locked at minimum level. | Alien attacks | engine disruption | none | C | - |
| 143 | cannot comply. | Command acknowledgement | refusal to comply | none | K | - |
| 144 | Frame Shift Drive charging. | Ship switches | FSD charging | Flags.FsdCharging 0 -> 1 | A | doc+log |
| 145 | Oxygen depleted. | Environment (on foot) | oxygen depleted | Flags2.LowOxygen or Status.Oxygen = 0 (EDDI: available, no event) | B | doc+EDDI+hyp |
| 146 | flight assist on | Ship switches | flight assist on | Flags.FlightAssistOff 1 -> 0 | A | doc+log |
| 147 | Warning, shield generator attack. | Alien attacks | attack on the shield generator | none | C | - |
| 148 | Your scooping complete. | Fuel | fuel scooping complete | end of scooping, tank full: Status.Fuel.FuelMain = capacity (EDDI: ShipRefuelledEvent) | B | EDDI+hyp |
| 149 | receiving fuel. | Fuel | receiving fuel | none | C | - |
| 150 | Warning, targeting Overload attack. Automatic weapons scrambled. | Alien attacks | targeting overload | none | C | - |
| 151 | accelerated shield regeneration. | Effects and modes | accelerated shield regeneration | none | C | - |
| 152 | Weapon enhanced. | Effects and modes | weapon enhanced | none | C | - |
| 153 | I'll repeat. | Command acknowledgement | "I'll repeat" | none | K | - |
| 154 | Mothership Under Attack | Fighter and mothership | mothership under attack | journal UnderAttack, field Target = Mothership (EDDI) | B | EDDI+hyp |
| 155 | Fighter recalled. | Fighter and mothership | fighter recalled | none | C | - |
| 156 | Warning, oxygen low. | Environment (on foot) | oxygen low | Flags2.LowOxygen or Status.Oxygen (EDDI: available, no event) | B | doc+EDDI+hyp |
| 157 | Under attack. | Hull and canopy | attack on the ship (variant) | journal UnderAttack, field Target = You/Fighter/Mothership (this second clip may be a variant per target) | A | log+EDDI+hyp |
| 158 | 3 | Self-destruct | countdown: three | timer from journal SelfDestruct, the countdown lasts about 31 s; the moment is still to be measured | B | log+hyp |
| 159 | Taking damage. | Hull and canopy | damage (variant) | journal HullDamage, fields PlayerPilot and Fighter (maybe a variant per target) | B | EDDI+hyp |
| 160 | ship dismissed | Fighter and mothership | crew or fighter sent away | none | C | - |
| 161 | cargo theft in progress | Cargo | cargo theft | none | C | - |
| 162 | Orbital flight engaged. | Effects and modes | orbital flight | journal ApproachBody | B | hyp |
| 163 | Fighter shields offline. | Fighter and mothership | fighter's shields are down | none | C | - |
| 164 | ship recalled | Fighter and mothership | crew or fighter recalled | none | C | - |
| 165 | Target destroyed. | Targets and combat | target destroyed (variant) | journal Bounty | B | hyp |
| 166 | passenger escape pod launched | Cargo | passenger escape pod | none | C | - |
| 167 | module delivery complete. | Docking and ships | module delivery complete | journal FetchRemoteModule plus timer (EDDI: ModuleArrivedEvent) | B | EDDI+hyp |
| 168 | canopy compromised | Hull and canopy | canopy damaged | journal CockpitBreached (EDDI: no variables) | B | EDDI+hyp |
| 169 | Handbrake is on. | Ship switches | SRV handbrake | Flags.SrvHandbrake 0 -> 1 | A | doc+log |
| 170 | Warning, thermal attack, gaining heat. | Alien attacks | thermal attack | none | C | - |
| 171 | Olympus drone error. | Limpets and mining | limpet error | none | C | - |
| 172 | receiving shield generation boost. | Effects and modes | shield boost from outside | none | C | - |
| 173 | Fighter, Resuming Formation | Fighter and mothership | fighter returns to formation | none | C | - |
| 174 | thrusters online | Module failures | thrusters on | none | C | - |
| 175 | hatch brake Olympic expired. | Limpets and mining | hatch breaker limpet expired | none | C | - |
| 176 | frameshift drive supercharged | Effects and modes | FSD supercharged (SCO) | Flags2.SupercruiseOverdrive | B | hyp |
| 177 | Five | Self-destruct | countdown: five | timer from journal SelfDestruct, the countdown lasts about 31 s; the moment is still to be measured | B | log+hyp |
| 178 | Fuel transfer limit failed. | Fuel | fuel transfer limit | none | C | - |
| 179 | speed surge | Effects and modes | speed surge | none | C | - |
| 180 | Prepare sequence successful. | Repairs | repair sequence successful | none | C | - |
| 181 | fighter, under attack. | Fighter and mothership | fighter under attack | journal UnderAttack, field Target = Fighter (EDDI) | B | EDDI+hyp |
| 182 | chassis repaired | Repairs | hull repaired | journal Repair or RepairAll (EDDI: ShipRepairedEvent) | B | EDDI+hyp |
| 183 | Warning, Capital Class Signature detected. | Anomalies, scans, navigation | capital ship signature | journal Music, MusicTrack = CapitalShip (from the list in the documentation) | B | doc+hyp |
| 184 | incoming telepresence request. | Multicrew | request to join | none | C | - |
| 185 | cargo scoop retracted | Ship switches | cargo scoop retracted | Flags.CargoScoopDeployed 1 -> 0 | A | doc+log |
| 186 | Unknown System. | Anomalies, scans, navigation | unknown system | none | C | - |
| 187 | thrusters offline | Module failures | thrusters off | none | C | - |
| 188 | Mothership holding position. | Fighter and mothership | mothership holds position | none | C | - |
| 189 | massive frame shift surge detected. | Anomalies, scans, navigation | massive FSD surge | none | C | - |
| 190 | incoming audio log. | Missions and messages | audio log | none | C | - |
