interface StatusBadgeProps {
  status: string;
}

const STATUS_STYLES: Record<string, string> = {
  running: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  queued: 'bg-yellow-100 text-yellow-700',
  stopped: 'bg-gray-100 text-gray-700',
  pending: 'bg-amber-100 text-amber-700',
  validated: 'bg-emerald-100 text-emerald-700',
  rejected: 'bg-red-100 text-red-700',
  approved: 'bg-green-100 text-green-700',
  'auto-approved': 'bg-blue-100 text-blue-700',
  'needs-review': 'bg-amber-100 text-amber-700',
};

export default function StatusBadge({ status }: StatusBadgeProps) {
  const style = STATUS_STYLES[status] || 'bg-gray-100 text-gray-700';
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {status}
    </span>
  );
}
