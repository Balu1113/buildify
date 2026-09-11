import React, { useEffect, useState } from 'react';
import { todoApi } from '../../api/todos';
import { PieChart, CheckCircle, Clock, AlertTriangle, List } from 'lucide-react';
import LoadingSpinner from '../ui/LoadingSpinner';

const MetricCard = ({ title, value, icon: Icon, colorClass }) => (
  <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 flex items-center gap-4">
    <div className={`p-3 rounded-lg ${colorClass}`}>
      <Icon className="w-6 h-6" />
    </div>
    <div>
      <p className="text-sm text-gray-500 font-medium">{title}</p>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
    </div>
  </div>
);

const DashboardMetrics = () => {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await todoApi.getDashboard();
        setMetrics(res.data);
      } catch (err) {
        setError("Failed to load dashboard metrics");
      } finally {
        setLoading(false);
      }
    };
    fetchMetrics();
  }, []);

  if (loading) return <LoadingSpinner className="my-12" />;
  if (error) return <div className="text-red-500">{error}</div>;
  if (!metrics) return null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
      <MetricCard
        title="Total Tasks"
        value={metrics.total}
        icon={List}
        colorClass="bg-blue-100 text-blue-600"
      />
      <MetricCard
        title="Pending"
        value={metrics.pending}
        icon={Clock}
        colorClass="bg-yellow-100 text-yellow-600"
      />
      <MetricCard
        title="Completed"
        value={metrics.completed}
        icon={CheckCircle}
        colorClass="bg-green-100 text-green-600"
      />
      <MetricCard
        title="High Priority"
        value={metrics.high_priority}
        icon={AlertTriangle}
        colorClass="bg-red-100 text-red-600"
      />
    </div>
  );
};

export default DashboardMetrics;