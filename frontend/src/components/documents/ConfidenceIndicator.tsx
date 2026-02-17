interface ConfidenceIndicatorProps {
  confidence: number;
}

export const ConfidenceIndicator: React.FC<ConfidenceIndicatorProps> = ({ confidence }) => {
  const percentage = Math.round(confidence * 100);
  const color = confidence >= 0.9 ? 'text-green-600' : confidence >= 0.7 ? 'text-yellow-600' : 'text-red-600';
  
  return (
    <span className={`font-semibold ${color}`}>
      {percentage}%
    </span>
  );
};
