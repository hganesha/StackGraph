export type Tier = 'enterprise' | 'growth' | 'startup';
export type MaturityLevel = 1 | 2 | 3 | 4 | 5;

export interface Capability {
  id: string;
  name: string;
  description: string;
  maturity?: MaturityLevel;
  tags?: string[];
  kpis?: string[];
  owner?: string;
}

export interface Process {
  id: string;
  name: string;
  description: string;
  capabilities: Capability[];
  icon?: string;
}

export interface BusinessFunction {
  id: string;
  name: string;
  description: string;
  color: string;
  gradient: string;
  icon: string;
  processes: Process[];
}

export interface ValueChainStep {
  id: string;
  label: string;
  sublabel: string;
  color: string;
  gradient: string;
  icon: string;
  order: number;
}

export const ORGANIZATION_UNIT_TEMPLATE: ValueChainStep[] = [
  { id: 'org:executive', label: 'Executive Office', sublabel: 'Enterprise direction', color: '38', gradient: '', icon: 'building', order: 0 },
  { id: 'org:growth', label: 'Product & Growth', sublabel: 'Markets and innovation', color: '38', gradient: '', icon: 'building', order: 1 },
  { id: 'org:operations', label: 'Operations', sublabel: 'Delivery and supply', color: '38', gradient: '', icon: 'building', order: 2 },
  { id: 'org:corporate', label: 'Corporate Services', sublabel: 'Enterprise enablement', color: '38', gradient: '', icon: 'building', order: 3 },
  { id: 'org:digital', label: 'Digital & Data', sublabel: 'Technology foundation', color: '38', gradient: '', icon: 'building', order: 4 },
];

// ─── VALUE CHAIN TEMPLATES ───────────────────────────────────────────────────

/**
 * `color` holds a HUE value (0-360). All tones are derived at render time
 * via the tonal ramp in theme.ts. `icon` holds an icon-registry key.
 */
export const VALUE_CHAIN_TEMPLATES: Record<string, ValueChainStep[]> = {
  porter: [
    { id: 'inbound', label: 'Inbound Logistics', sublabel: 'Receiving & storage', color: '243', gradient: '', icon: 'package', order: 0 },
    { id: 'operations', label: 'Operations', sublabel: 'Transformation', color: '281', gradient: '', icon: 'cog', order: 1 },
    { id: 'outbound', label: 'Outbound Logistics', sublabel: 'Distribution', color: '344', gradient: '', icon: 'truck', order: 2 },
    { id: 'marketing', label: 'Marketing & Sales', sublabel: 'Demand generation', color: '16', gradient: '', icon: 'megaphone', order: 3 },
    { id: 'service', label: 'Service', sublabel: 'After-sales support', color: '38', gradient: '', icon: 'lifebuoy', order: 4 },
  ],
  digital: [
    { id: 'discover', label: 'Discover', sublabel: 'Insight & research', color: '206', gradient: '', icon: 'search', order: 0 },
    { id: 'design', label: 'Design', sublabel: 'Product & experience', color: '243', gradient: '', icon: 'pen', order: 1 },
    { id: 'develop', label: 'Develop', sublabel: 'Build & engineer', color: '281', gradient: '', icon: 'code', order: 2 },
    { id: 'deploy', label: 'Deploy', sublabel: 'Release & scale', color: '152', gradient: '', icon: 'rocket', order: 3 },
    { id: 'delight', label: 'Delight', sublabel: 'Retain & grow', color: '38', gradient: '', icon: 'sparkle', order: 4 },
  ],
  retail: [
    { id: 'source', label: 'Sourcing', sublabel: 'Procurement & supply', color: '152', gradient: '', icon: 'globe', order: 0 },
    { id: 'store', label: 'Store Operations', sublabel: 'Inventory & fulfilment', color: '206', gradient: '', icon: 'store', order: 1 },
    { id: 'sell', label: 'Commerce', sublabel: 'Omnichannel sales', color: '281', gradient: '', icon: 'cart', order: 2 },
    { id: 'serve', label: 'Customer Service', sublabel: 'Support & returns', color: '344', gradient: '', icon: 'message', order: 3 },
    { id: 'sustain', label: 'Sustainability', sublabel: 'ESG & compliance', color: '16', gradient: '', icon: 'leaf', order: 4 },
  ],
  custom: [
    { id: 'strategy', label: 'Strategy', sublabel: 'Direction & planning', color: '243', gradient: '', icon: 'target', order: 0 },
    { id: 'execute', label: 'Execution', sublabel: 'Deliver & operate', color: '281', gradient: '', icon: 'zap', order: 1 },
    { id: 'measure', label: 'Measure', sublabel: 'Monitor & learn', color: '206', gradient: '', icon: 'chart', order: 2 },
    { id: 'optimize', label: 'Optimise', sublabel: 'Improve & scale', color: '152', gradient: '', icon: 'refresh', order: 3 },
  ],
};

// ─── BUSINESS CAPABILITY LIBRARY ─────────────────────────────────────────────

export const BUSINESS_FUNCTIONS: BusinessFunction[] = [
  {
    id: 'strategy',
    name: 'Strategy & Corporate Development',
    description: 'Defines direction, portfolio, and growth agenda',
    color: '#6366f1',
    gradient: 'from-indigo-500 to-violet-600',
    icon: '🎯',
    processes: [
      {
        id: 'strategic-planning',
        name: 'Strategic Planning',
        description: 'Long-range planning and scenario analysis',
        capabilities: [
          { id: 'cap-1', name: 'Strategic Vision Setting', description: 'Define 3-5 year directional ambition and strategic intent', tags: ['planning', 'leadership'], kpis: ['Strategy clarity score', 'Leadership alignment %'] },
          { id: 'cap-2', name: 'Scenario Planning & Horizon Scanning', description: 'Structured foresight and alternative future modeling', tags: ['planning', 'risk'], kpis: ['# Scenarios modeled', 'Signal detection rate'] },
          { id: 'cap-3', name: 'OKR & Goal Cascading', description: 'Translate strategy into measurable objectives across layers', tags: ['execution', 'alignment'], kpis: ['OKR attainment %', 'Cascade depth'] },
          { id: 'cap-4', name: 'Strategic Resource Allocation', description: 'Portfolio prioritization and capital redeployment', tags: ['finance', 'planning'], kpis: ['ROIC', 'Portfolio reallocation speed'] },
          { id: 'cap-5', name: 'Competitive Intelligence', description: 'Systematic competitor and market monitoring', tags: ['insight', 'intelligence'], kpis: ['Insight-to-action rate', 'Coverage breadth'] },
        ],
      },
      {
        id: 'corp-dev',
        name: 'Corporate Development',
        description: 'M&A, partnerships, and venture activity',
        capabilities: [
          { id: 'cap-6', name: 'M&A Origination & Screening', description: 'Pipeline development and deal sourcing', tags: ['M&A', 'growth'], kpis: ['Deal pipeline size', 'Conversion rate'] },
          { id: 'cap-7', name: 'Due Diligence Management', description: 'Commercial, financial, and operational diligence', tags: ['M&A', 'risk'], kpis: ['Diligence cycle time', 'Surprise rate post-close'] },
          { id: 'cap-8', name: 'Post-Merger Integration', description: 'Value realization and culture integration', tags: ['M&A', 'integration'], kpis: ['Synergy capture %', 'Retention of key talent'] },
          { id: 'cap-9', name: 'Strategic Partnerships & JVs', description: 'Alliance formation and governance', tags: ['growth', 'partnerships'], kpis: ['Partnership revenue contribution', 'JV health score'] },
          { id: 'cap-10', name: 'Venture & Ecosystem Building', description: 'Corporate venture capital and startup engagement', tags: ['innovation', 'growth'], kpis: ['Portfolio IRR', '# Active ventures'] },
        ],
      },
    ],
  },
  {
    id: 'innovation',
    name: 'Innovation & Product',
    description: 'Drives new product development and innovation pipeline',
    color: '#8b5cf6',
    gradient: 'from-violet-500 to-purple-600',
    icon: '💡',
    processes: [
      {
        id: 'product-strategy',
        name: 'Product Strategy & Roadmap',
        description: 'Product vision, portfolio and go-to-market planning',
        capabilities: [
          { id: 'cap-11', name: 'Product Vision & Positioning', description: 'Define product market fit and differentiated value proposition', tags: ['product', 'strategy'], kpis: ['NPS', 'Market share'] },
          { id: 'cap-12', name: 'Roadmap Planning & Prioritization', description: 'Feature sequencing aligned to business outcomes', tags: ['product', 'planning'], kpis: ['On-time delivery %', 'Feature adoption rate'] },
          { id: 'cap-13', name: 'Portfolio Management', description: 'Lifecycle management across product portfolio', tags: ['product', 'portfolio'], kpis: ['Portfolio ROI', 'EOL management'] },
          { id: 'cap-14', name: 'Pricing & Monetization Strategy', description: 'Pricing architecture, value-based models, packaging', tags: ['revenue', 'strategy'], kpis: ['Revenue per user', 'Pricing elasticity'] },
        ],
      },
      {
        id: 'rnd',
        name: 'Research & Development',
        description: 'Applied research and innovation pipeline',
        capabilities: [
          { id: 'cap-15', name: 'Technology Scouting & IP Management', description: 'Emerging tech assessment and patent strategy', tags: ['R&D', 'technology'], kpis: ['Patent applications', 'Tech readiness level'] },
          { id: 'cap-16', name: 'Design Thinking & Rapid Prototyping', description: 'Human-centered design and iterative experimentation', tags: ['design', 'innovation'], kpis: ['Prototype cycle time', 'User validation score'] },
          { id: 'cap-17', name: 'Stage-Gate Innovation Process', description: 'Structured funnel from idea to launch', tags: ['innovation', 'process'], kpis: ['Ideas-to-launch ratio', 'Innovation funnel velocity'] },
          { id: 'cap-18', name: 'Open Innovation & Co-creation', description: 'External partner and customer-driven innovation', tags: ['innovation', 'ecosystem'], kpis: ['External idea contribution %', 'Co-created revenue'] },
        ],
      },
      {
        id: 'product-delivery',
        name: 'Product Delivery & Engineering',
        description: 'Agile development and release management',
        capabilities: [
          { id: 'cap-19', name: 'Agile & DevOps Delivery', description: 'Sprint-based delivery with CI/CD pipelines', tags: ['engineering', 'agile'], kpis: ['Deployment frequency', 'Lead time to change'] },
          { id: 'cap-20', name: 'Quality Engineering & Testing', description: 'Automated testing and quality assurance', tags: ['quality', 'engineering'], kpis: ['Defect escape rate', 'Test automation %'] },
          { id: 'cap-21', name: 'Platform & API Management', description: 'Internal developer platform and API ecosystem', tags: ['platform', 'engineering'], kpis: ['Developer experience score', 'API uptime %'] },
        ],
      },
    ],
  },
  {
    id: 'customer',
    name: 'Customer & Market',
    description: 'Acquires, grows, and retains customers across all channels',
    color: '#ec4899',
    gradient: 'from-pink-500 to-rose-600',
    icon: '❤️',
    processes: [
      {
        id: 'marketing',
        name: 'Marketing & Brand',
        description: 'Demand generation and brand equity building',
        capabilities: [
          { id: 'cap-22', name: 'Brand Strategy & Architecture', description: 'Brand identity, portfolio and governance', tags: ['brand', 'strategy'], kpis: ['Brand equity index', 'Aided awareness %'] },
          { id: 'cap-23', name: 'Demand Generation & Performance Marketing', description: 'Paid, owned, earned media orchestration', tags: ['marketing', 'growth'], kpis: ['CAC', 'ROAS', 'Pipeline generated'] },
          { id: 'cap-24', name: 'Content Strategy & Marketing', description: 'Editorial planning and content supply chain', tags: ['content', 'marketing'], kpis: ['Content engagement rate', 'Share of voice'] },
          { id: 'cap-25', name: 'Customer Segmentation & Targeting', description: 'Behavioral and needs-based segmentation', tags: ['insight', 'marketing'], kpis: ['Segment share', 'Targeting precision'] },
          { id: 'cap-26', name: 'Marketing Analytics & Attribution', description: 'Multi-touch attribution and marketing mix modeling', tags: ['analytics', 'marketing'], kpis: ['Attribution accuracy', 'Marketing ROI'] },
        ],
      },
      {
        id: 'sales',
        name: 'Sales & Revenue',
        description: 'Pipeline management and deal execution',
        capabilities: [
          { id: 'cap-27', name: 'Sales Strategy & Coverage Model', description: 'Channel design, territory and quota setting', tags: ['sales', 'strategy'], kpis: ['Quota attainment %', 'Revenue per rep'] },
          { id: 'cap-28', name: 'Account Planning & Management', description: 'Strategic account development and expansion', tags: ['sales', 'accounts'], kpis: ['Account growth rate', 'Wallet share %'] },
          { id: 'cap-29', name: 'Sales Enablement & Productivity', description: 'Tools, training and content for sales effectiveness', tags: ['enablement', 'sales'], kpis: ['Ramp time', 'Win rate'] },
          { id: 'cap-30', name: 'Revenue Operations (RevOps)', description: 'CRM, process and data alignment across revenue teams', tags: ['operations', 'revenue'], kpis: ['Forecast accuracy', 'Pipeline velocity'] },
          { id: 'cap-31', name: 'Partner & Channel Management', description: 'Indirect sales and channel development', tags: ['channels', 'sales'], kpis: ['Channel revenue %', 'Partner satisfaction'] },
        ],
      },
      {
        id: 'cx',
        name: 'Customer Experience',
        description: 'End-to-end experience design and measurement',
        capabilities: [
          { id: 'cap-32', name: 'Customer Journey Orchestration', description: 'Cross-channel experience design and activation', tags: ['CX', 'journey'], kpis: ['CSAT', 'Journey completion rate'] },
          { id: 'cap-33', name: 'Voice of Customer (VoC) Program', description: 'Structured listening and closed-loop feedback', tags: ['CX', 'insight'], kpis: ['NPS', 'Feedback resolution rate'] },
          { id: 'cap-34', name: 'Loyalty & Retention Management', description: 'Churn prediction and retention interventions', tags: ['loyalty', 'retention'], kpis: ['Churn rate', 'LTV', 'Loyalty member share'] },
          { id: 'cap-35', name: 'Customer Service Operations', description: 'Omnichannel service delivery and resolution', tags: ['service', 'operations'], kpis: ['First contact resolution', 'AHT', 'CSAT'] },
        ],
      },
    ],
  },
  {
    id: 'operations',
    name: 'Operations & Supply Chain',
    description: 'Delivers products and services efficiently and reliably',
    color: '#10b981',
    gradient: 'from-emerald-500 to-teal-600',
    icon: '⚙️',
    processes: [
      {
        id: 'supply-chain',
        name: 'Supply Chain Management',
        description: 'End-to-end supply chain planning and execution',
        capabilities: [
          { id: 'cap-36', name: 'Demand & Supply Planning', description: 'Statistical forecasting and S&OP process', tags: ['planning', 'supply chain'], kpis: ['Forecast accuracy', 'Inventory turns'] },
          { id: 'cap-37', name: 'Procurement & Strategic Sourcing', description: 'Supplier selection, negotiation and contracting', tags: ['procurement', 'sourcing'], kpis: ['Savings vs. baseline', 'Supplier on-time delivery'] },
          { id: 'cap-38', name: 'Logistics & Distribution', description: 'Transportation management and last-mile delivery', tags: ['logistics', 'distribution'], kpis: ['On-time delivery %', 'Cost per shipment'] },
          { id: 'cap-39', name: 'Warehouse & Inventory Management', description: 'Storage optimization and fulfillment execution', tags: ['warehouse', 'inventory'], kpis: ['Inventory accuracy', 'Order fulfillment rate'] },
          { id: 'cap-40', name: 'Supply Chain Risk Management', description: 'Disruption sensing and supply resilience', tags: ['risk', 'supply chain'], kpis: ['Supplier risk score', 'Business continuity coverage'] },
        ],
      },
      {
        id: 'manufacturing',
        name: 'Manufacturing & Production',
        description: 'Production planning, quality and lean operations',
        capabilities: [
          { id: 'cap-41', name: 'Production Planning & Scheduling', description: 'Capacity management and MRP/ERP integration', tags: ['manufacturing', 'planning'], kpis: ['OEE', 'Schedule adherence'] },
          { id: 'cap-42', name: 'Quality Management System (QMS)', description: 'ISO-aligned quality control and assurance', tags: ['quality', 'manufacturing'], kpis: ['First-pass yield', 'DPMO', 'Audit findings'] },
          { id: 'cap-43', name: 'Lean / Continuous Improvement', description: 'Kaizen, 5S, and waste elimination programs', tags: ['lean', 'operational excellence'], kpis: ['Waste reduction %', 'Cycle time improvement'] },
          { id: 'cap-44', name: 'Asset & Maintenance Management', description: 'Predictive and preventive maintenance strategy', tags: ['assets', 'maintenance'], kpis: ['MTBF', 'MTTR', 'Asset utilization'] },
        ],
      },
    ],
  },
  {
    id: 'technology',
    name: 'Technology & Digital',
    description: 'Builds and operates the technology foundation',
    color: '#3b82f6',
    gradient: 'from-blue-500 to-cyan-600',
    icon: '💻',
    processes: [
      {
        id: 'data-analytics',
        name: 'Data & Analytics',
        description: 'Data management, analytics and AI/ML capabilities',
        capabilities: [
          { id: 'cap-45', name: 'Data Governance & Master Data Management', description: 'Data quality, ownership and lineage', tags: ['data', 'governance'], kpis: ['Data quality score', 'MDM coverage %'] },
          { id: 'cap-46', name: 'Advanced Analytics & Insights', description: 'Descriptive, predictive and prescriptive analytics', tags: ['analytics', 'data'], kpis: ['Insight-to-action time', 'Model adoption rate'] },
          { id: 'cap-47', name: 'AI & Machine Learning Platform', description: 'MLOps and enterprise AI governance', tags: ['AI', 'ML'], kpis: ['Model accuracy', 'AI use cases deployed'] },
          { id: 'cap-48', name: 'Data Monetization', description: 'Internal and external value creation from data assets', tags: ['data', 'revenue'], kpis: ['Data product revenue', 'API call volume'] },
        ],
      },
      {
        id: 'it-operations',
        name: 'IT & Platform Operations',
        description: 'Infrastructure, security and enterprise applications',
        capabilities: [
          { id: 'cap-49', name: 'Cloud Strategy & FinOps', description: 'Multi-cloud architecture and cost optimization', tags: ['cloud', 'infrastructure'], kpis: ['Cloud cost efficiency', 'Uptime SLA'] },
          { id: 'cap-50', name: 'Cybersecurity & Risk Management', description: 'Zero-trust security and threat response', tags: ['security', 'risk'], kpis: ['Mean time to detect', 'Security posture score'] },
          { id: 'cap-51', name: 'Enterprise Architecture', description: 'Technology portfolio and integration strategy', tags: ['architecture', 'IT'], kpis: ['Technical debt ratio', 'Architecture compliance %'] },
          { id: 'cap-52', name: 'IT Service Management (ITSM)', description: 'Incident, change and problem management', tags: ['ITSM', 'operations'], kpis: ['MTTR', 'Change success rate'] },
        ],
      },
      {
        id: 'digital-transformation',
        name: 'Digital Transformation',
        description: 'Digital strategy and transformation execution',
        capabilities: [
          { id: 'cap-53', name: 'Digital Strategy & Business Model Innovation', description: 'Digital opportunity identification and investment thesis', tags: ['digital', 'strategy'], kpis: ['Digital revenue %', 'Disruption readiness index'] },
          { id: 'cap-54', name: 'Automation & Process Mining', description: 'RPA, intelligent automation and process discovery', tags: ['automation', 'efficiency'], kpis: ['FTE automation equivalents', 'Process cycle time reduction'] },
          { id: 'cap-55', name: 'Digital Customer Engagement', description: 'App, portal and digital touchpoint management', tags: ['digital', 'CX'], kpis: ['Digital adoption rate', 'Digital CSAT'] },
        ],
      },
    ],
  },
  {
    id: 'finance',
    name: 'Finance & Risk',
    description: 'Stewards financial performance and enterprise risk',
    color: '#f59e0b',
    gradient: 'from-amber-500 to-orange-600',
    icon: '💰',
    processes: [
      {
        id: 'financial-management',
        name: 'Financial Management',
        description: 'Planning, reporting and decision support',
        capabilities: [
          { id: 'cap-56', name: 'Financial Planning & Analysis (FP&A)', description: 'Budgeting, forecasting and business partnering', tags: ['finance', 'planning'], kpis: ['Forecast accuracy', 'Budget variance %'] },
          { id: 'cap-57', name: 'Management Reporting & Insights', description: 'Timely, accurate financial performance reporting', tags: ['reporting', 'finance'], kpis: ['Reporting cycle time', 'Insight utilization rate'] },
          { id: 'cap-58', name: 'Treasury & Capital Management', description: 'Cash, liquidity and capital structure optimization', tags: ['treasury', 'capital'], kpis: ['Cash conversion cycle', 'WACC'] },
          { id: 'cap-59', name: 'Tax Strategy & Compliance', description: 'Effective tax planning and regulatory compliance', tags: ['tax', 'compliance'], kpis: ['Effective tax rate', 'Compliance coverage'] },
        ],
      },
      {
        id: 'risk-compliance',
        name: 'Risk & Compliance',
        description: 'Enterprise risk framework and regulatory compliance',
        capabilities: [
          { id: 'cap-60', name: 'Enterprise Risk Management (ERM)', description: 'Risk identification, quantification and treatment', tags: ['risk', 'governance'], kpis: ['Risk register coverage', 'Residual risk score'] },
          { id: 'cap-61', name: 'Internal Controls & Audit', description: 'Control environment and assurance activities', tags: ['controls', 'audit'], kpis: ['Control effectiveness %', 'Audit findings closure rate'] },
          { id: 'cap-62', name: 'Regulatory Affairs & Compliance', description: 'Monitoring, interpretation and adherence to regulation', tags: ['regulatory', 'compliance'], kpis: ['Regulatory incidents', 'Compliance training completion'] },
          { id: 'cap-63', name: 'Insurance & Loss Prevention', description: 'Risk transfer and operational risk mitigation', tags: ['insurance', 'risk'], kpis: ['Total cost of risk', 'Loss ratio'] },
        ],
      },
    ],
  },
  {
    id: 'people',
    name: 'People & Organization',
    description: 'Attracts, develops and enables great talent',
    color: '#f43f5e',
    gradient: 'from-rose-500 to-pink-600',
    icon: '👥',
    processes: [
      {
        id: 'talent',
        name: 'Talent Management',
        description: 'End-to-end talent lifecycle management',
        capabilities: [
          { id: 'cap-64', name: 'Workforce Planning & Analytics', description: 'Strategic headcount and skills forecasting', tags: ['HR', 'workforce'], kpis: ['Vacancy fill rate', 'Workforce plan accuracy'] },
          { id: 'cap-65', name: 'Talent Acquisition & Employer Branding', description: 'Recruiting strategy and candidate experience', tags: ['talent', 'recruiting'], kpis: ['Time-to-hire', 'Quality of hire', 'Offer acceptance rate'] },
          { id: 'cap-66', name: 'Performance Management', description: 'Goal setting, evaluation and continuous feedback', tags: ['performance', 'HR'], kpis: ['Performance rating distribution', 'Feedback frequency'] },
          { id: 'cap-67', name: 'Learning & Development', description: 'Skills development and leadership programs', tags: ['learning', 'development'], kpis: ['Training hours per employee', 'Skills gap closure rate'] },
          { id: 'cap-68', name: 'Succession Planning & Leadership Pipeline', description: 'Critical role readiness and leadership bench', tags: ['succession', 'leadership'], kpis: ['Succession coverage %', 'Internal fill rate'] },
        ],
      },
      {
        id: 'org-effectiveness',
        name: 'Organizational Effectiveness',
        description: 'Culture, change and organizational design',
        capabilities: [
          { id: 'cap-69', name: 'Culture & Employee Engagement', description: 'Culture shaping and eNPS measurement', tags: ['culture', 'engagement'], kpis: ['eNPS', 'Engagement index', 'Retention rate'] },
          { id: 'cap-70', name: 'Change Management', description: 'Structured change and adoption programs', tags: ['change', 'transformation'], kpis: ['Change adoption rate', 'Resistance index'] },
          { id: 'cap-71', name: 'Organizational Design', description: 'Structure, spans, layers and governance', tags: ['org design', 'governance'], kpis: ['Span of control', 'Decision velocity'] },
          { id: 'cap-72', name: 'Total Rewards & Compensation', description: 'Compensation philosophy and benefits strategy', tags: ['rewards', 'HR'], kpis: ['Pay equity ratio', 'Benefits utilization'] },
        ],
      },
    ],
  },
  {
    id: 'legal',
    name: 'Legal & Governance',
    description: 'Protects the enterprise and ensures ethical conduct',
    color: '#64748b',
    gradient: 'from-slate-500 to-gray-600',
    icon: '⚖️',
    processes: [
      {
        id: 'legal-ops',
        name: 'Legal Operations',
        description: 'Contract management and legal service delivery',
        capabilities: [
          { id: 'cap-73', name: 'Contract Lifecycle Management', description: 'Drafting, negotiation, execution and obligation tracking', tags: ['legal', 'contracts'], kpis: ['Contract cycle time', 'Contract risk score'] },
          { id: 'cap-74', name: 'Intellectual Property Management', description: 'Patent, trademark and trade secret protection', tags: ['IP', 'legal'], kpis: ['IP portfolio value', 'IP enforcement rate'] },
          { id: 'cap-75', name: 'Litigation & Dispute Management', description: 'Dispute resolution and outside counsel management', tags: ['litigation', 'legal'], kpis: ['Legal spend per revenue', 'Case resolution time'] },
        ],
      },
      {
        id: 'esg',
        name: 'ESG & Sustainability',
        description: 'Environmental, social and governance program management',
        capabilities: [
          { id: 'cap-76', name: 'ESG Strategy & Reporting', description: 'Material ESG commitment and stakeholder disclosure', tags: ['ESG', 'sustainability'], kpis: ['ESG rating score', 'Disclosure completeness'] },
          { id: 'cap-77', name: 'Carbon & Climate Management', description: 'Scope 1-3 emissions tracking and net zero roadmap', tags: ['climate', 'sustainability'], kpis: ['Scope 1-2 emissions', 'Reduction trajectory vs. target'] },
          { id: 'cap-78', name: 'Ethics & Business Conduct', description: 'Code of conduct, ethics hotline and investigation', tags: ['ethics', 'governance'], kpis: ['Ethics training completion', 'Substantiated incidents'] },
        ],
      },
    ],
  },
];

export const ALL_CAPABILITIES: Capability[] = BUSINESS_FUNCTIONS.flatMap(bf =>
  bf.processes.flatMap(p => p.capabilities)
);
