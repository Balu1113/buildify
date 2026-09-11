import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search, Filter, SortAsc, FilterX } from 'lucide-react';

const TodoFilters = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  const updateFilter = (key, value) => {
    const newParams = new URLSearchParams(searchParams);
    if (value && value !== 'all') {
      newParams.set(key, value);
    } else {
      newParams.delete(key);
    }
    setSearchParams(newParams);
  };

  const clearFilters = () => setSearchParams({});

  const status = searchParams.get('status') || 'all';
  const priority = searchParams.get('priority') || 'all';
  const ordering = searchParams.get('ordering') || '';
  const search = searchParams.get('search') || '';

  return (
    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 space-y-4">
      <div className="flex flex-col md:flex-row md:items-center gap-4">
        {/* Search */}
        <div className="relative flex-grow">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search todos..."
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 outline-none"
            value={search}
            onChange={(e) => updateFilter('search', e.target.value)}
          />
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-500" />
            <select
              className="border border-gray-300 rounded-md px-2 py-2 text-sm bg-white"
              value={status}
              onChange={(e) => updateFilter('status', e.target.value)}
            >
              <option value="all">All Statuses</option>
              <option value="pending">Pending</option>
              <option value="completed">Completed</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <select
              className="border border-gray-300 rounded-md px-2 py-2 text-sm bg-white"
              value={priority}
              onChange={(e) => updateFilter('priority', e.target.value)}
            >
              <option value="all">All Priorities</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <SortAsc className="w-4 h-4 text-gray-500" />
            <select
              className="border border-gray-300 rounded-md px-2 py-2 text-sm bg-white"
              value={ordering}
              onChange={(e) => updateFilter('ordering', e.target.value)}
            >
              <option value="">Sort By</option>
              <option value="-created_at">Newest First</option>
              <option value="created_at">Oldest First</option>
              <option value="-due_date">Due Soonest</option>
              <option value="due_date">Due Latest</option>
              <option value="-priority">High Priority</option>
              <option value="priority">Low Priority</option>
            </select>
          </div>

          {(search || status !== 'all' || priority !== 'all' || ordering) && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-1 text-sm text-red-600 hover:text-red-800"
            >
              <FilterX className="w-4 h-4" />
              Clear
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default TodoFilters;