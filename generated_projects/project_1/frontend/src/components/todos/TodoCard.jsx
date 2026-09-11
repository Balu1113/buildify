import React from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { Calendar, CheckCircle2, Circle, Clock, AlertCircle } from 'lucide-react';

const TodoCard = ({ todo, onToggleStatus, onEdit, onDelete }) => {
  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'high': return 'text-red-600 bg-red-100';
      case 'medium': return 'text-orange-600 bg-orange-100';
      case 'low': return 'text-green-600 bg-green-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 hover:shadow-md transition-shadow group">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggleStatus(todo);
            }}
            className={`mt-1 transition-colors ${todo.status === 'completed' ? 'text-green-500' : 'text-gray-300 hover:text-blue-500'}`}
          >
            {todo.status === 'completed' ? <CheckCircle2 className="w-6 h-6" /> : <Circle className="w-6 h-6" />}
          </button>
          
          <div>
            <h3 className={`text-lg font-semibold ${todo.status === 'completed' ? 'line-through text-gray-400' : 'text-gray-900'}`}>
              <Link to={`/todos/${todo.id}`}>{todo.title}</Link>
            </h3>
            <p className="text-sm text-gray-600 mt-1 line-clamp-2">{todo.description}</p>
          </div>
        </div>
        
        <div className="flex flex-col items-end gap-2">
          <span className={`text-xs font-bold px-2 py-1 rounded-full uppercase ${getPriorityColor(todo.priority)}`}>
            {todo.priority}
          </span>
          {todo.due_date && (
            <div className="flex items-center text-xs text-gray-500">
              <Calendar className="w-3 h-3 mr-1" />
              {format(new Date(todo.due_date), 'MMM d')}
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 pt-4 border-t border-gray-50 flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={() => onEdit(todo)}
          className="text-sm text-blue-600 hover:underline px-2 py-1"
        >
          Edit
        </button>
        <button
          onClick={() => onDelete(todo.id)}
          className="text-sm text-red-600 hover:underline px-2 py-1"
        >
          Delete
        </button>
      </div>
    </div>
  );
};

export default TodoCard;