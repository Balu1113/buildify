import React from 'react';
import Layout from '../components/layout/Layout';
import DashboardMetrics from '../components/todos/DashboardMetrics';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import Button from '../components/ui/Button';

const DashboardPage = () => {
  return (
    <Layout>
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Welcome back!</h1>
          <p className="text-gray-600 mt-2">Here is an overview of your productivity today.</p>
        </div>

        <DashboardMetrics />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white p-8 rounded-xl shadow-sm border border-gray-200 flex flex-col justify-center items-center text-center space-y-4">
            <h3 className="text-xl font-semibold text-gray-900">Ready to work?</h3>
            <p className="text-gray-500">View all your tasks or create a new one to keep your momentum going.</p>
            <Link to="/todos">
               <Button className="w-full">
                 Manage My Tasks <ArrowRight className="ml-2 w-4 h-4" />
               </Button>
            </Link>
          </div>
          
          <div className="bg-blue-600 p-8 rounded-xl shadow-sm text-white flex flex-col justify-center items-center text-center space-y-4">
             <h3 className="text-2xl font-bold">Productivity Tip</h3>
             <p className="text-blue-100">Break large tasks into smaller, manageable sub-tasks to avoid feeling overwhelmed.</p>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default DashboardPage;