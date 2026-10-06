export type ScenarioCategoryId =
  | 'home_station'
  | 'deployed_location'
  | 'airshow_open_house'
  | 'joint_exercise'
  | 'combat_theater'
  | 'humanitarian_assistance'
  | 'garrison_training'
  | 'special_event';

export type ScenarioEventTypeId =
  | 'inbound_missile'
  | 'drone_attack'
  | 'cbrne'
  | 'active_shooter'
  | 'explosion_blast'
  | 'aircraft_mishap'
  | 'mass_casualty_incident'
  | 'earthquake'
  | 'tsunami'
  | 'hurricane_typhoon'
  | 'wildfire'
  | 'vehicle_accident'
  | 'heat_stress'
  | 'cold_weather_injury'
  | 'structural_collapse'
  | 'cyber_attack_cascading'
  | 'crowd_surge'
  | 'hazmat_release'
  | 'biological_agent'
  | 'chemical_agent'
  | 'radiological_exposure'
  | 'nuclear_detonation'
  | 'unexploded_ordnance'
  | 'indirect_fire'
  | 'sniper_attack';

export interface ScenarioSpecificOption {
  id: string;
  label: string;
  description: string;
  narrativeDetail: string;
}

export interface ScenarioEventTypeOption {
  id: ScenarioEventTypeId;
  label: string;
  description: string;
  specifics: ScenarioSpecificOption[];
}

export interface ScenarioCategoryOption {
  id: ScenarioCategoryId;
  label: string;
  description: string;
  settingNarrative: string;
  eventTypeIds: ScenarioEventTypeId[];
}

const SPECIFICS = {
  inbound_missile: [
    {
      id: 'flightline_impact',
      label: 'Flightline impact',
      description: 'Primary impact near flightline operations',
      narrativeDetail: 'Inbound missile impact reported on the flightline. Fragmentation and blast casualties expected.',
    },
    {
      id: 'housing_impact',
      label: 'Housing / dormitory impact',
      description: 'Impact in base housing area',
      narrativeDetail: 'Missile impact in base housing. Mixed trauma profiles with delayed extrication.',
    },
    {
      id: 'clinic_inbound',
      label: 'Clinic receiving inbound casualties',
      description: 'Facility intact; casualties en route',
      narrativeDetail: 'Clinic not directly hit. Multiple casualties inbound via CASEVAC and self-referral.',
    },
    {
      id: 'shelter_in_place',
      label: 'Shelter-in-place active',
      description: 'Personnel sheltered during attack sequence',
      narrativeDetail: 'Personnel sheltered during missile event. Casualties arrive after all-clear with staggered severity.',
    },
    {
      id: 'secondary_strike',
      label: 'Secondary strike wave',
      description: 'Follow-on attack during response',
      narrativeDetail: 'Follow-on strike reported during initial response. Comms degraded and resource surge ongoing.',
    },
  ],
  drone_attack: [
    {
      id: 'logistics_yard',
      label: 'Logistics yard strike',
      description: 'Drone strike near supply/logistics area',
      narrativeDetail: 'Loitering munition strike on logistics yard. Multiple walking wounded and one critical.',
    },
    {
      id: 'perimeter_breach',
      label: 'Perimeter breach',
      description: 'UAS breach at installation perimeter',
      narrativeDetail: 'Small UAS detonation at perimeter checkpoint. Security and medical response overlapping.',
    },
    {
      id: 'swarm_attack',
      label: 'Swarm / multi-drone',
      description: 'Multiple drones in sequence',
      narrativeDetail: 'Multiple drone incursions reported. Wide-area minor injuries plus focal critical casualties.',
    },
    {
      id: 'combined_arms',
      label: 'Combined with indirect fire',
      description: 'Drone attack followed by indirect fire',
      narrativeDetail: 'Drone strike followed by indirect fire. Triage under continued threat.',
    },
  ],
  cbrne: [
    {
      id: 'unknown_release',
      label: 'Unknown agent release',
      description: 'Agent not yet identified',
      narrativeDetail: 'Unknown CBRNE release suspected. Decon corridors establishing; symptomatic patients arriving.',
    },
    {
      id: 'nerve_agent_suspected',
      label: 'Nerve agent suspected',
      description: 'SLUDGE-type symptoms reported',
      narrativeDetail: 'Nerve agent suspected based on field reports. Antidote caches activated.',
    },
    {
      id: 'industrial_chemical',
      label: 'Industrial chemical spill',
      description: 'Hazmat from industrial source',
      narrativeDetail: 'Industrial chemical release on base. Respiratory and dermal complaints increasing.',
    },
    {
      id: 'radiological_suspected',
      label: 'Radiological material suspected',
      description: 'Possible radiological contamination',
      narrativeDetail: 'Radiological contamination suspected. Monitoring teams and survey en route.',
    },
    {
      id: 'biological_suspicion',
      label: 'Biological agent suspicion',
      description: 'Illness cluster with unusual pattern',
      narrativeDetail: 'Unusual illness cluster reported. Isolation and public health notification initiated.',
    },
  ],
  active_shooter: [
    {
      id: 'facility_interior',
      label: 'Facility interior',
      description: 'Shooter inside occupied building',
      narrativeDetail: 'Active shooter inside occupied facility. Casualties triaged after lockdown lift.',
    },
    {
      id: 'open_area',
      label: 'Open assembly area',
      description: 'Shooter in open gathering area',
      narrativeDetail: 'Active shooter in open assembly area. Multiple GSW and panic injuries.',
    },
    {
      id: 'vehicle_ramming',
      label: 'Vehicle + small arms',
      description: 'Combined vehicle and shooter event',
      narrativeDetail: 'Vehicle ramming combined with small-arms fire. Mixed blunt and penetrating trauma.',
    },
  ],
  explosion_blast: [
    {
      id: 'ied_detonation',
      label: 'IED detonation',
      description: 'Improvised explosive device',
      narrativeDetail: 'IED detonation reported. Primary, secondary blast, and fragmentation injuries.',
    },
    {
      id: 'fuel_explosion',
      label: 'Fuel / POL explosion',
      description: 'Fuel storage or POL incident',
      narrativeDetail: 'Fuel/POL explosion with burn and blast injuries. Evacuation corridors active.',
    },
    {
      id: 'ammunition_cookoff',
      label: 'Ammunition cook-off',
      description: 'Ammunition storage event',
      narrativeDetail: 'Ammunition cook-off event. Fragmentation injuries at standoff distance.',
    },
  ],
  aircraft_mishap: [
    {
      id: 'runway_crash',
      label: 'Runway crash landing',
      description: 'Aircraft crash on or near runway',
      narrativeDetail: 'Aircraft crash landing on runway. Potential mass burn and blunt trauma casualties.',
    },
    {
      id: 'ground_maintenance',
      label: 'Ground maintenance mishap',
      description: 'Maintenance-related aircraft incident',
      narrativeDetail: 'Aircraft ground maintenance mishap. Focused crush and burn injuries.',
    },
    {
      id: 'airshow_demo',
      label: 'Airshow demonstration mishap',
      description: 'Public airshow flight incident',
      narrativeDetail: 'Airshow demonstration mishap. Public and military casualties possible.',
    },
  ],
  mass_casualty_incident: [
    {
      id: 'triage_primary',
      label: 'Primary triage site',
      description: 'Initial MCI triage establishment',
      narrativeDetail: 'Mass casualty incident declared. Establish triage and treatment sectors.',
    },
    {
      id: 'facility_surge',
      label: 'Medical facility surge',
      description: 'Hospital/clinic receiving MCI influx',
      narrativeDetail: 'Medical facility in MCI surge. Prioritize life-threatening interventions.',
    },
    {
      id: 'expectant_care',
      label: 'Expectant / resource limited',
      description: 'Resources overwhelmed',
      narrativeDetail: 'Resources overwhelmed. Expectant care protocols may apply per local guidance.',
    },
  ],
  earthquake: [
    {
      id: 'building_collapse',
      label: 'Building collapse',
      description: 'Structural collapse with entrapment',
      narrativeDetail: 'Earthquake with building collapse. Crush injuries and delayed extrication.',
    },
    {
      id: 'aftershock_sequence',
      label: 'Aftershock sequence',
      description: 'Ongoing aftershocks during response',
      narrativeDetail: 'Aftershocks continuing during medical response. Re-triage required.',
    },
  ],
  tsunami: [
    {
      id: 'coastal_inundation',
      label: 'Coastal inundation',
      description: 'Coastal base flooding',
      narrativeDetail: 'Tsunami inundation of coastal facilities. Drowning, lacerations, hypothermia.',
    },
  ],
  hurricane_typhoon: [
    {
      id: 'pre_landfall',
      label: 'Pre-landfall injuries',
      description: 'Injuries during preparation/evacuation',
      narrativeDetail: 'Hurricane pre-landfall injuries during preparation and partial evacuation.',
    },
    {
      id: 'post_storm_surge',
      label: 'Post-storm medical surge',
      description: 'Injuries after storm passage',
      narrativeDetail: 'Post-storm medical surge. Limited power and supply chain disruption.',
    },
  ],
  wildfire: [
    {
      id: 'smoke_inhalation',
      label: 'Smoke inhalation cluster',
      description: 'Respiratory casualties from smoke',
      narrativeDetail: 'Wildfire smoke inhalation cluster. Evacuation routes compromised.',
    },
    {
      id: 'burn_evacuation',
      label: 'Burn casualties during evacuation',
      description: 'Burns during fire evacuation',
      narrativeDetail: 'Burn casualties during wildfire evacuation. Transport assets limited.',
    },
  ],
  vehicle_accident: [
    {
      id: 'convoy_rollover',
      label: 'Convoy rollover',
      description: 'Military convoy accident',
      narrativeDetail: 'Convoy rollover with multiple occupants. Blunt trauma and entrapment.',
    },
    {
      id: 'airfield_vehicle',
      label: 'Airfield vehicle strike',
      description: 'Vehicle strike on airfield',
      narrativeDetail: 'Vehicle strike on airfield operations area. Mixed trauma profiles.',
    },
  ],
  heat_stress: [
    {
      id: 'training_exertional',
      label: 'Training exertional heat illness',
      description: 'Heat casualties during training',
      narrativeDetail: 'Exertional heat illness cluster during field training. Rapid cooling required.',
    },
    {
      id: 'deployed_heat_wave',
      label: 'Deployed heat wave',
      description: 'Sustained extreme heat operations',
      narrativeDetail: 'Sustained heat wave during deployed operations. Dehydration and heat stroke presentations.',
    },
  ],
  cold_weather_injury: [
    {
      id: 'hypothermia_frostbite',
      label: 'Hypothermia / frostbite',
      description: 'Cold exposure casualties',
      narrativeDetail: 'Cold weather injuries during extended outdoor operations.',
    },
    {
      id: 'transport_delay',
      label: 'Evacuation delay in cold',
      description: 'Delayed transport in winter conditions',
      narrativeDetail: 'Evacuation delayed in cold conditions. Deterioration during prolonged field care.',
    },
  ],
  structural_collapse: [
    {
      id: 'hangar_collapse',
      label: 'Hangar / large structure',
      description: 'Large structure collapse',
      narrativeDetail: 'Large structure collapse. Search and extraction ongoing.',
    },
    {
      id: 'partial_collapse',
      label: 'Partial collapse / entrapment',
      description: 'Partial structural failure',
      narrativeDetail: 'Partial structural collapse with entrapment. Crush syndrome risk.',
    },
  ],
  cyber_attack_cascading: [
    {
      id: 'comms_degraded',
      label: 'Comms / systems degraded',
      description: 'Medical systems affected indirectly',
      narrativeDetail: 'Cyber attack degraded comms and patient tracking systems. Manual workflows required.',
    },
  ],
  crowd_surge: [
    {
      id: 'airshow_crowd',
      label: 'Airshow crowd crush',
      description: 'Crowd surge at public event',
      narrativeDetail: 'Crowd surge at airshow/open house. Crush asphyxia and minor trauma.',
    },
    {
      id: 'gate_surge',
      label: 'Installation gate surge',
      description: 'Mass gathering at entry point',
      narrativeDetail: 'Mass gathering surge at installation entry. Multiple minor casualties.',
    },
  ],
  hazmat_release: [
    {
      id: 'lab_spill',
      label: 'Laboratory spill',
      description: 'Controlled facility hazmat release',
      narrativeDetail: 'Laboratory hazmat spill. Exposure assessments underway.',
    },
    {
      id: 'transport_spill',
      label: 'Transport spill',
      description: 'Hazmat during transport',
      narrativeDetail: 'Hazmat release during transport on base. Downwind precautions initiated.',
    },
  ],
  biological_agent: [
    {
      id: 'respiratory_cluster',
      label: 'Respiratory illness cluster',
      description: 'Unusual respiratory presentation cluster',
      narrativeDetail: 'Unusual respiratory illness cluster. Isolation and sampling protocols active.',
    },
  ],
  chemical_agent: [
    {
      id: 'skin_eye_exposure',
      label: 'Skin / eye exposure',
      description: 'Dermal and ocular chemical exposure',
      narrativeDetail: 'Chemical exposure with skin and eye symptoms. Decon lanes established.',
    },
  ],
  radiological_exposure: [
    {
      id: 'survey_positive',
      label: 'Radiation survey positive',
      description: 'Positive radiological survey',
      narrativeDetail: 'Radiological survey positive in operational area. Exposure triage initiated.',
    },
  ],
  nuclear_detonation: [
    {
      id: 'distant_detonation',
      label: 'Distant detonation effects',
      description: 'Fallout / blast at distance',
      narrativeDetail: 'Distant nuclear detonation effects. Fallout planning and burn/blast casualties.',
    },
  ],
  unexploded_ordnance: [
    {
      id: 'uxo_discovery',
      label: 'UXO discovery during ops',
      description: 'UXO found during operations',
      narrativeDetail: 'UXO discovery during operations. Blast injury from secondary detonation.',
    },
  ],
  indirect_fire: [
    {
      id: 'mortar_attack',
      label: 'Mortar attack',
      description: 'Indirect fire on FOB',
      narrativeDetail: 'Mortar attack on forward operating base. Fragmentation and blast injuries.',
    },
    {
      id: 'rocket_attack',
      label: 'Rocket attack',
      description: 'Rocket barrage',
      narrativeDetail: 'Rocket barrage reported. Multiple impact sites with scattered casualties.',
    },
  ],
  sniper_attack: [
    {
      id: 'perimeter_sniper',
      label: 'Perimeter sniper fire',
      description: 'Sniper fire from outside wire',
      narrativeDetail: 'Sniper fire from outside perimeter. GSW casualties with ongoing threat.',
    },
  ],
} as const satisfies Record<ScenarioEventTypeId, ScenarioSpecificOption[]>;

export const SCENARIO_EVENT_TYPES: ScenarioEventTypeOption[] = (
  Object.keys(SPECIFICS) as ScenarioEventTypeId[]
).map((id) => {
  const labels: Record<ScenarioEventTypeId, { label: string; description: string }> = {
    inbound_missile: { label: 'Inbound missile', description: 'Ballistic or cruise missile attack on installation' },
    drone_attack: { label: 'Drone / UAS attack', description: 'Loitering munition or UAS strike' },
    cbrne: { label: 'CBRNE (general)', description: 'Combined chemical, biological, radiological, nuclear, explosive' },
    active_shooter: { label: 'Active shooter', description: 'Active shooter or mass violence' },
    explosion_blast: { label: 'Explosion / blast', description: 'Blast or detonation event' },
    aircraft_mishap: { label: 'Aircraft mishap', description: 'Aviation accident or incident' },
    mass_casualty_incident: { label: 'Mass casualty incident (MCI)', description: 'Declared MCI exceeding local capacity' },
    earthquake: { label: 'Earthquake', description: 'Seismic event with structural damage' },
    tsunami: { label: 'Tsunami', description: 'Coastal inundation event' },
    hurricane_typhoon: { label: 'Hurricane / typhoon', description: 'Tropical cyclone impact' },
    wildfire: { label: 'Wildfire', description: 'Fire threat to installation or training area' },
    vehicle_accident: { label: 'Vehicle accident', description: 'Ground vehicle mishap' },
    heat_stress: { label: 'Heat stress / heat illness', description: 'Environmental heat casualties' },
    cold_weather_injury: { label: 'Cold weather injury', description: 'Hypothermia, frostbite, cold exposure' },
    structural_collapse: { label: 'Structural collapse', description: 'Building or structure failure' },
    cyber_attack_cascading: { label: 'Cyber attack (cascading effects)', description: 'Cyber incident affecting medical ops' },
    crowd_surge: { label: 'Crowd surge / stampede', description: 'Crowd crush at event or gathering' },
    hazmat_release: { label: 'Hazmat release', description: 'Hazardous materials release' },
    biological_agent: { label: 'Biological agent', description: 'Suspected biological warfare or outbreak' },
    chemical_agent: { label: 'Chemical agent', description: 'Suspected chemical agent exposure' },
    radiological_exposure: { label: 'Radiological exposure', description: 'Radiological contamination or exposure' },
    nuclear_detonation: { label: 'Nuclear detonation', description: 'Nuclear weapon effects' },
    unexploded_ordnance: { label: 'Unexploded ordnance (UXO)', description: 'UXO-related injury or threat' },
    indirect_fire: { label: 'Indirect fire', description: 'Mortars, rockets, artillery' },
    sniper_attack: { label: 'Sniper attack', description: 'Precision fire from sniper' },
  };

  return {
    id,
    label: labels[id].label,
    description: labels[id].description,
    specifics: [...SPECIFICS[id]],
  };
});

export const SCENARIO_CATEGORIES: ScenarioCategoryOption[] = [
  {
    id: 'home_station',
    label: 'Home station',
    description: 'CONUS or OCONUS permanent installation',
    settingNarrative: 'You are operating at home station on a USAF installation.',
    eventTypeIds: [
      'inbound_missile', 'drone_attack', 'cbrne', 'active_shooter', 'explosion_blast',
      'aircraft_mishap', 'mass_casualty_incident', 'earthquake', 'hurricane_typhoon',
      'wildfire', 'vehicle_accident', 'heat_stress', 'cold_weather_injury', 'structural_collapse',
      'cyber_attack_cascading', 'crowd_surge', 'hazmat_release', 'biological_agent',
      'chemical_agent', 'radiological_exposure', 'unexploded_ordnance', 'indirect_fire',
    ],
  },
  {
    id: 'deployed_location',
    label: 'Deployed location',
    description: 'Forward deployed or contingency location',
    settingNarrative: 'You are deployed to a contingency location with limited resources.',
    eventTypeIds: [
      'inbound_missile', 'drone_attack', 'cbrne', 'explosion_blast', 'indirect_fire',
      'sniper_attack', 'mass_casualty_incident', 'vehicle_accident', 'heat_stress',
      'cold_weather_injury', 'unexploded_ordnance', 'biological_agent', 'chemical_agent',
      'radiological_exposure', 'active_shooter',
    ],
  },
  {
    id: 'airshow_open_house',
    label: 'Airshow / open house',
    description: 'Public aviation event on base',
    settingNarrative: 'You are supporting a public airshow or open house with large crowds on base.',
    eventTypeIds: [
      'aircraft_mishap', 'crowd_surge', 'heat_stress', 'mass_casualty_incident',
      'vehicle_accident', 'active_shooter', 'explosion_blast', 'drone_attack',
    ],
  },
  {
    id: 'joint_exercise',
    label: 'Joint exercise',
    description: 'Multi-service or coalition training exercise',
    settingNarrative: 'You are participating in a joint training exercise with simulated real-world stressors.',
    eventTypeIds: [
      'explosion_blast', 'indirect_fire', 'cbrne', 'mass_casualty_incident', 'vehicle_accident',
      'heat_stress', 'cold_weather_injury', 'drone_attack', 'active_shooter', 'unexploded_ordnance',
    ],
  },
  {
    id: 'combat_theater',
    label: 'Combat theater',
    description: 'High-threat combat operations environment',
    settingNarrative: 'You are in a combat theater with ongoing threat to force.',
    eventTypeIds: [
      'indirect_fire', 'sniper_attack', 'explosion_blast', 'drone_attack', 'cbrne',
      'mass_casualty_incident', 'unexploded_ordnance', 'vehicle_accident', 'active_shooter',
    ],
  },
  {
    id: 'humanitarian_assistance',
    label: 'Humanitarian assistance',
    description: 'HA/DR or humanitarian mission',
    settingNarrative: 'You are supporting humanitarian assistance with austere conditions.',
    eventTypeIds: [
      'earthquake', 'tsunami', 'hurricane_typhoon', 'mass_casualty_incident', 'structural_collapse',
      'heat_stress', 'wildfire', 'vehicle_accident', 'biological_agent',
    ],
  },
  {
    id: 'garrison_training',
    label: 'Garrison training',
    description: 'Scheduled field training on installation',
    settingNarrative: 'You are in a scheduled garrison training evolution.',
    eventTypeIds: [
      'heat_stress', 'cold_weather_injury', 'vehicle_accident', 'explosion_blast',
      'mass_casualty_incident', 'cbrne', 'active_shooter',
    ],
  },
  {
    id: 'special_event',
    label: 'Special event',
    description: 'Distinguished visitor, ceremony, or large gathering',
    settingNarrative: 'You are supporting a special event with elevated medical standby.',
    eventTypeIds: [
      'crowd_surge', 'heat_stress', 'active_shooter', 'vehicle_accident', 'mass_casualty_incident',
      'drone_attack', 'cbrne',
    ],
  },
];

export interface ScenarioSelection {
  categoryId: ScenarioCategoryId;
  eventTypeId: ScenarioEventTypeId;
  specificId: string;
}

export const DEFAULT_SCENARIO_SELECTION: ScenarioSelection = {
  categoryId: 'home_station',
  eventTypeId: 'inbound_missile',
  specificId: 'clinic_inbound',
};

export function getCategoryById(id: ScenarioCategoryId): ScenarioCategoryOption | undefined {
  return SCENARIO_CATEGORIES.find((c) => c.id === id);
}

export function getEventTypeById(id: ScenarioEventTypeId): ScenarioEventTypeOption | undefined {
  return SCENARIO_EVENT_TYPES.find((e) => e.id === id);
}

export function getEventTypesForCategory(categoryId: ScenarioCategoryId): ScenarioEventTypeOption[] {
  const category = getCategoryById(categoryId);
  if (!category) return SCENARIO_EVENT_TYPES;
  return SCENARIO_EVENT_TYPES.filter((e) => category.eventTypeIds.includes(e.id));
}

export function getSpecificsForEvent(eventTypeId: ScenarioEventTypeId): ScenarioSpecificOption[] {
  return getEventTypeById(eventTypeId)?.specifics ?? [];
}

export function getSpecificOption(
  eventTypeId: ScenarioEventTypeId,
  specificId: string,
): ScenarioSpecificOption | undefined {
  return getSpecificsForEvent(eventTypeId).find((s) => s.id === specificId);
}

export function normalizeScenarioSelection(selection: ScenarioSelection): ScenarioSelection {
  const category = getCategoryById(selection.categoryId) ?? SCENARIO_CATEGORIES[0];
  const events = getEventTypesForCategory(category.id);
  const eventType = events.find((e) => e.id === selection.eventTypeId) ?? events[0];
  const specifics = getSpecificsForEvent(eventType.id);
  const specific = specifics.find((s) => s.id === selection.specificId) ?? specifics[0];

  return {
    categoryId: category.id,
    eventTypeId: eventType.id,
    specificId: specific?.id ?? selection.specificId,
  };
}
