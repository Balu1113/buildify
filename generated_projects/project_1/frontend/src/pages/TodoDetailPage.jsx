import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { todoApi } from '../api/todos';
import Layout from '../components/layout/Layout';
import TodoDetails from '../components/todos/TodoDetails';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import ErrorMessage from '../components/ui/ErrorMessage';

const TodoDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [todo, setTodo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isEditing, setIsEditing] = useState(false);

  const fetchTodo = async () => {
    try {
      const res = await todoApi.get(id);
      setTodo(res.data);
    } catch (err) {
      setError("Todo not found");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTodo();
  }, [id]);

  if (loading) return <Layout><LoadingSpinner className="my-12" /></Layout>;
  if (error) return <Layout><ErrorMessage message={error} /></Layout>;
  if (!todo) return null;

  return (
    <Layout>
      {isEditing ? (
        <TodoForm 
          initialData={todo} 
          onClose={() => setIsEditing(false)} 
        />
      ) : (
        <TodoDetails 
          onEdit={() => setIsEditing(true)} 
        />
      )}
    </Layout>
  );
};

export default TodoDetailPage;