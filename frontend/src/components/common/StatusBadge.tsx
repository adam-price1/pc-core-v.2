interface StatusBadgeProps {
  status: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const colors: Record<string, string> = {
    'needs-review': 'bg-yellow-100 text-yellow-800',
    'auto-approved': 'bg-green-100 text-green-800',
    'approved': 'bg-blue-100 text-blue-800',
  };
  
  return (
    <span className={`px-2 py-1 text-xs font-semibold rounded-full ${colors[status] || 'bg-gray-100 text-gray-800'}`}>
      {status}
    </span>
  );
};
