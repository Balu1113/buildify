import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { todoApi } from '../../api/todos';
import { Calendar, CheckCircle2, Circle, ArrowLeft, Edit2, Trash2 } from 'lucide-react';
import Button from '../ui/Button';
import LoadingSpinner from '../ui/LoadingSpinner';
import ErrorMessage from '../ui/ErrorMessage';
import { format } from 'date-fns';

const TodoDetails = ({ onEdit }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [todo, setTodo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchTodo = async () => {
      try {
        const res = await todoApi.get(id);
        setTodo(res.data);
      } catch (err) {
        setError("Todo not found or access denied");
      } finally {
        setLoading(false);
      }
    };
    fetchTodo();
  }, [id]);

  if (loading) return <LoadingSpinner className="my-12" />;
  if (error) return <ErrorMessage message={error} />;
  if (!todo) return null;

  return (
    <div className="max-w-3xl mx-auto">
      <button
        onClick={() => navigate('/todos')}
        className="flex items-center text-gray-600 hover:text-blue-600 mb-6 transition-colors"
      >
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to List
      </button>

      <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-gray-200">
        <div className={`h-2 w-full ${todo.status === 'completed' ? 'bg-green-500' : 'bg-blue-500'}`} />
        <div className="p-8">
          <div className="flex justify-between items-start">
            <div className="flex-grow">
              <h1 className="text-3xl font-bold text-gray-900 mb-2">{todo.title}</h1>
              <div className="flex flex-wrap gap-3 mb-6">
                <span className={`px-3 py-1 rounded-full text-sm font-semibold uppercase ${ 
                  todo.priority === 'high' ? 'bg-red-100 text-red-700' : 
                  todo.priority === 'medium' ? 'bg-orange-100 text-orange-700' : 
                  'bg-green-100 text-green-700'
                }`}>
                  {todo.priority}
                </span>
                <span className={`px-3 py-1 rounded-full text-sm font-semibold uppercase ${ 
                  todo.status === 'completed' ? 'bg-green-100 text-green-700' : 
                  'bg-blue-100 text-blue-700'
                }`}>
                  {todo.status}
                </span>
                {todo.due_date && (
                  <div className="flex items-center text-sm text-gray-500">
                    <Calendar className="w-4 h-4 mr-1" />
                    Due {format(new Date(todo.due_date), 'PPP')}
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div>
              <h4 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-2">Description</h4>
              <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">
                {todo.description || <span className="italic text-gray-400">No description provided.</span>}
              </p>
            </div>

            <div className="pt-6 border-t border-gray-100 flex justify-end gap-4">
              <Button variant="outline" onClick={() => onEdit(todo)}>
                <Edit2 className="w-4 h-4 mr-2" /> Edit
              </Button>
              <Button variant="danger" onClick={() => navigate(`/todos/${id}/delete`)}>
                <Trash2 className="w-4 h-4 mr-2" /> Delete
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TodoDetails;