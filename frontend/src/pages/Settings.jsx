import React from 'react'
import { useState, useEffect } from "react"
import { rawMaterial, configApi, auth } from "../api/client"
import Modal from "../components/Modal"
import PopupDialog from "../components/PopupDialog"
import usePinGate from "../hooks/usePinGate"
import { formatDateTimeIST } from "../utils/datetime"
import eyeoff from "../pages/assets/eye.png"
import eye from "../pages/assets/eye-off.png"
const EMPTY_RECIPE_MATERIAL = { rm_name: "", quantity: "" }

const initialRecipeForm = () => ({
  name: "",
  materials: [{ ...EMPTY_RECIPE_MATERIAL }],
})

export default function Settings() {
  const { requestPin, pinDialog } = usePinGate()
  const [showPinModal, setShowPinModal] = useState(false);
  const [showNewPin, setShowNewPin] = useState(false);
const [showConfirmPin, setShowConfirmPin] = useState(false);
  const [rmTypes, setRmTypes] = useState([])
  const [productTypes, setProductTypes] = useState([])
  const [recipes, setRecipes] = useState([])
  const [newRmType, setNewRmType] = useState("")
  const [showEditRmType, setShowEditRmType] = useState(false)
  const [rmTypeError, setRmTypeError] = useState('')
  const [editingRmType, setEditingRmType] = useState(null)
  const [rmTypeFormName, setRmTypeFormName] = useState("")
  const [showEditProductType, setShowEditProductType] = useState(false)
  const [productTypeError, setProductTypeError] = useState('')
  const [editingProductType, setEditingProductType] = useState(null)
  const [productTypeFormName, setProductTypeFormName] = useState("")
  const [showAddRecipe, setShowAddRecipe] = useState(false)
  const [recipeError, setRecipeError] = useState('')
  const [editingRecipeId, setEditingRecipeId] = useState(null)
  const [recipeForm, setRecipeForm] = useState(initialRecipeForm)
  const [popupMessage, setPopupMessage] = useState('')
  const [rmTypeToDelete, setRmTypeToDelete] = useState(null)
  const [productTypeToDelete, setProductTypeToDelete] = useState(null)
  const [recipeToDelete, setRecipeToDelete] = useState(null)
  const [pinForm, setPinForm] = useState({ current_pin: '', new_pin: '', confirm_pin: '' })
  const [pinError, setPinError] = useState('')
  const [pinSuccess, setPinSuccess] = useState('')
  const [pinSaving, setPinSaving] = useState(false)

  const load = () => {
    rawMaterial.listTypes().then(({ data }) => setRmTypes(Array.isArray(data) ? data : []))
    configApi.productTypesManage().then(({ data }) => setProductTypes(Array.isArray(data) ? data : []))
    configApi.recipes().then(({ data }) => setRecipes(Array.isArray(data) ? data : []))
  }

  useEffect(() => { load() }, [])

  const addRmType = async () => {
    if (!newRmType.trim()) return
    await rawMaterial.addType(newRmType)
    setNewRmType("")
    load()
  }

  const openEditRmTypeModal = (type) => {
    setEditingRmType(type)
    setRmTypeFormName(type?.name || "")
    setShowEditRmType(true)
  }

  const closeEditRmTypeModal = () => {
    setShowEditRmType(false)
    setEditingRmType(null)
    setRmTypeFormName("")
    setRmTypeError('')
  }

  const saveRmTypeEdit = async (e) => {
    e.preventDefault()
    setRmTypeError('')
    if (!editingRmType) return
    const value = rmTypeFormName.trim()
    if (!value || value === editingRmType.name) {
      closeEditRmTypeModal()
      return
    }
    try {
      await rawMaterial.updateType(editingRmType.id, value)
      closeEditRmTypeModal()
      load()
    } catch (err) {
      const detail = err?.response?.data?.detail || "Unable to update raw material type."
      setRmTypeError(detail)
    }
  }

  const deleteRmType = async (type) => {
    setRmTypeToDelete(type)
  }

  const confirmDeleteRmType = async () => {
    if (!rmTypeToDelete) return
    try {
      await rawMaterial.deleteType(rmTypeToDelete.id)
      setRmTypeToDelete(null)
      load()
    } catch (err) {
      const detail = err?.response?.data?.detail || "Unable to delete raw material type."
      setRmTypeToDelete(null)
      setPopupMessage(detail)
    }
  }

  const openEditProductTypeModal = (type) => {
    setEditingProductType(type)
    setProductTypeFormName(type?.name || "")
    setProductTypeError('')
    setShowEditProductType(true)
  }

  const closeEditProductTypeModal = () => {
    setShowEditProductType(false)
    setEditingProductType(null)
    setProductTypeFormName("")
    setProductTypeError('')
  }

  const saveProductTypeEdit = async (e) => {
    e.preventDefault()
    setProductTypeError('')
    if (!editingProductType) return
    const value = productTypeFormName.trim()
    if (!value || value === editingProductType.name) {
      closeEditProductTypeModal()
      return
    }
    try {
      await configApi.updateProductType(editingProductType.id, value)
      closeEditProductTypeModal()
      load()
    } catch (err) {
      const detail = err?.response?.data?.detail || "Unable to update product type."
      setProductTypeError(detail)
    }
  }

  const deleteProductType = async (type) => {
    setProductTypeToDelete(type)
  }

  const confirmDeleteProductType = async () => {
    if (!productTypeToDelete) return
    try {
      await configApi.deleteProductType(productTypeToDelete.id)
      setProductTypeToDelete(null)
      load()
    } catch (err) {
      const detail = err?.response?.data?.detail || "Unable to delete product type."
      setProductTypeToDelete(null)
      setPopupMessage(detail)
    }
  }

  const addRecipeRow = () => {
    setRecipeForm((prev) => ({
      ...prev,
      materials: [...prev.materials, { ...EMPTY_RECIPE_MATERIAL }],
    }))
  }

  const removeRecipeRow = (index) => {
    setRecipeForm((prev) => ({
      ...prev,
      materials: prev.materials.length === 1
        ? [{ ...EMPTY_RECIPE_MATERIAL }]
        : prev.materials.filter((_, i) => i !== index),
    }))
  }

  const updateRecipeRow = (index, field, value) => {
    setRecipeForm((prev) => ({
      ...prev,
      materials: prev.materials.map((row, i) => (
        i === index ? { ...row, [field]: value } : row
      )),
    }))
  }

  const closeRecipeModal = () => {
    setShowAddRecipe(false)
    setEditingRecipeId(null)
    setRecipeForm(initialRecipeForm())
    setRecipeError('')
  }

  const openAddRecipeModal = () => {
    setEditingRecipeId(null)
    setRecipeForm(initialRecipeForm())
    setRecipeError('')
    setShowAddRecipe(true)
  }

  const openEditRecipeModal = (recipe) => {
    const materials = Array.isArray(recipe?.materials) && recipe.materials.length > 0
      ? recipe.materials.map((item) => ({
          rm_name: item.rm_name || "",
          quantity: String(item.quantity ?? ""),
        }))
      : [{ ...EMPTY_RECIPE_MATERIAL }]

    setEditingRecipeId(recipe?.id ?? null)
    setRecipeForm({
      name: recipe?.name || "",
      materials,
      created_at: recipe?.created_at || null,
    })
    setRecipeError('')
    setShowAddRecipe(true)
  }

  const handleSaveRecipe = async (e) => {
    e.preventDefault()
    setRecipeError('')

    const materials = recipeForm.materials
      .map((item) => ({
        rm_name: (item.rm_name || "").trim(),
        quantity: item.quantity === "" ? NaN : parseFloat(item.quantity),
      }))
      .filter((item) => item.rm_name !== "" || !Number.isNaN(item.quantity))

    if (!recipeForm.name.trim()) {
      setRecipeError("Recipe name is required.")
      return
    }
    if (materials.length === 0) {
      setRecipeError("Add at least one raw material.")
      return
    }
    if (materials.some((item) => !item.rm_name || Number.isNaN(item.quantity) || item.quantity <= 0)) {
      setRecipeError("Each row must include raw material and weight greater than 0.")
      return
    }

    try {
      if (editingRecipeId) {
        await configApi.updateRecipe(editingRecipeId, {
          name: recipeForm.name.trim(),
          materials,
        })
      } else {
        await configApi.addRecipe({
          name: recipeForm.name.trim(),
          materials,
        })
      }
      closeRecipeModal()
      load()
    } catch (err) {
      const detail = err?.response?.data?.detail || `Unable to ${editingRecipeId ? "update" : "add"} recipe.`
      setRecipeError(detail)
    }
  }

  const deleteRecipe = async (recipe) => {
    setRecipeToDelete(recipe)
  }

  const confirmDeleteRecipe = async () => {
    if (!recipeToDelete) return
    try {
      await configApi.deleteRecipe(recipeToDelete.id)
      setRecipeToDelete(null)
      load()
    } catch (err) {
      const detail = err?.response?.data?.detail || "Unable to delete recipe."
      setRecipeToDelete(null)
      setPopupMessage(detail)
    }
  }
const handleClosePinModal = () => {
  setShowPinModal(false);

  // Reset form fields
  setPinForm({
    current_pin: "",
    new_pin: "",
    confirm_pin: "",
  });

  // Clear messages
  setPinError("");
  setPinSuccess("");

  // Reset eye toggle (optional but clean)
  setShowNewPin(false);
  setShowConfirmPin(false);
};

  const changePin = async (e) => {
    e.preventDefault()
    setPinError('')
    setPinSuccess('')

    if (!/^\d{4}$/.test(pinForm.current_pin) || !/^\d{4}$/.test(pinForm.new_pin)) {
      setPinError('PIN must be exactly 4 digits.')
      return
    }
    if (pinForm.new_pin !== pinForm.confirm_pin) {
      setPinError('New PIN and confirm PIN do not match.')
      return
    }
    if (pinForm.current_pin === pinForm.new_pin) {
      setPinError('New PIN must be different from current PIN.')
      return
    }

    try {
      setPinSaving(true)
      await auth.changePin(pinForm.current_pin, pinForm.new_pin)
      setPinForm({ current_pin: '', new_pin: '', confirm_pin: '' })
      setPinSuccess('PIN updated successfully.')
      setPinForm({
  current_pin: "",
  new_pin: "",
  confirm_pin: "",
});
     
    } catch (err) {
      setPinError(err?.response?.data?.detail || 'Unable to update PIN.')
    } finally {
      setPinSaving(false)
    }
  }

  return (
    <div>
      <div className='flex items-center justify-between '>
      <h1 className="text-xl font-semibold mb-8">Settings</h1>
       <div>
  <button
    onClick={() => setShowPinModal(true)}
    className="bg-[#245658] hover:bg-[#1d4446] text-white px-6 py-2 rounded-lg shadow-md transition mb-5"
  >
    Change Settings PIN
  </button>
</div>

{/* Modal */}
{showPinModal && (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
    
    {/* Modal Box */}
    <div className="bg-white w-full max-w-lg rounded-xl shadow-2xl p-6 relative animate-fadeIn">
      
      {/* Close Button */}
      <button
       onClick={handleClosePinModal}
        className="absolute top-3 right-3 text-gray-500 hover:text-black text-lg font-bold"
      >
        ✕
      </button>

      <h2 className="text-lg font-semibold mb-5 text-gray-800">
        Update Settings PIN
      </h2>

      <form onSubmit={changePin} className="space-y-4">

        {/* Current PIN */}
        <div>
          <label className="block text-sm text-gray-600 mb-1">
            Current PIN
          </label>
          <input
            type="password"
            inputMode="numeric"
            maxLength={4}
            value={pinForm.current_pin}
            onChange={(e) =>
              setPinForm((f) => ({
                ...f,
                current_pin: e.target.value.replace(/\D/g, "").slice(0, 4),
              }))
            }
            className="w-full border border-gray-300 px-3 py-2 rounded-lg focus:ring-2 focus:ring-[#245658] focus:outline-none"
            placeholder="1234"
            required
          />
        </div>

        {/* New PIN */}
        <div className="relative">
          <label className="block text-sm text-gray-600 mb-1">
            New PIN
          </label>
          <input
            type={showNewPin ? "text" : "password"}
            inputMode="numeric"
            maxLength={4}
            value={pinForm.new_pin}
            onChange={(e) =>
              setPinForm((f) => ({
                ...f,
                new_pin: e.target.value.replace(/\D/g, "").slice(0, 4),
              }))
            }
            className="w-full border border-gray-300 px-3 py-2 pr-10 rounded-lg focus:ring-2 focus:ring-[#245658] focus:outline-none"
            placeholder="New 4-digit PIN"
            required
          />

          {/* Eye Icon */}
          <img
            src={showNewPin ? eyeoff : eye}
            alt="toggle"
            onClick={() => setShowNewPin(!showNewPin)}
            className="absolute right-3 top-9 w-5 h-5 cursor-pointer"
          />
        </div>

        {/* Confirm PIN */}
        <div className="relative">
          <label className="block text-sm text-gray-600 mb-1">
            Confirm PIN
          </label>
          <input
            type={showConfirmPin ? "text" : "password"}
            inputMode="numeric"
            maxLength={4}
            value={pinForm.confirm_pin}
            onChange={(e) =>
              setPinForm((f) => ({
                ...f,
                confirm_pin: e.target.value.replace(/\D/g, "").slice(0, 4),
              }))
            }
            className="w-full border border-gray-300 px-3 py-2 pr-10 rounded-lg focus:ring-2 focus:ring-[#245658] focus:outline-none"
            placeholder="Re-enter new PIN"
            required
          />

          {/* Eye Icon */}
          <img
            src={showConfirmPin ? eyeoff : eye}
            alt="toggle"
            onClick={() => setShowConfirmPin(!showConfirmPin)}
            className="absolute right-3 top-9 w-5 h-5 cursor-pointer"
          />
        </div>

        <button
          type="submit"
          disabled={pinSaving}
          className="w-full bg-[#245658] hover:bg-[#1d4446] text-white py-2 rounded-lg transition disabled:opacity-60"
        >
          {pinSaving ? "Updating..." : "Update PIN"}
        </button>

        {pinError && (
          <div className="bg-red-100 text-red-800 px-3 py-2 rounded text-sm border border-red-300">
            {pinError}
          </div>
        )}

        {pinSuccess && (
          <div className="bg-green-100 text-green-800 px-3 py-2 rounded text-sm border border-green-300">
            {pinSuccess}
          </div>
        )}
      </form>
    </div>
  </div>
)}
</div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* RM TYPES - LEFT COLUMN */}
        <div className="border border-gray-400 rounded-lg p-4">
          <h2 className="font-medium mb-3">Raw Material Types</h2>

          <div className="flex gap-2 mb-3">
            <input
              value={newRmType}
              onChange={(e)=>setNewRmType(e.target.value)}
              placeholder="Enter RM Type"
              className="border px-3 py-2 rounded flex-1"
            />
            <button
              onClick={addRmType}
              className="bg-[#245658] text-white px-4 py-2 rounded"
            >
              Add
            </button>
          </div>

          <div className="mt-4  rounded-md p-3 bg-slate-50">
            <p className="text-sm font-medium text-slate-700 mb-2">
              Available Raw Material Types ({rmTypes.length})
            </p>
            {rmTypes.length === 0 ? (
              <p className="text-sm text-slate-500">No raw material types found.</p>
            ) : (
              <ul className="space-y-2 text-slate-700">
                {rmTypes.map((t) => (
                  <li key={t.id} className="flex items-center justify-between gap-2 border border-slate-200 rounded-md bg-white px-3 py-2">
                    <div>
                      <span>{t.name}</span>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <p className="text-xs text-slate-500">
                        Last Modified: {formatDateTimeIST(t.last_modified_at || t.created_at)}
                      </p>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => requestPin(
                            () => openEditRmTypeModal(t),
                            { title: 'PIN Required', message: 'Enter PIN to edit (1234) raw material type.' }
                          )}
                          className="px-3 py-1 rounded border border-gray-400 text-xs text-gray-800 hover:bg-gray-100"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => requestPin(
                            () => deleteRmType(t),
                            { title: 'PIN Required', message: 'Enter PIN to delete raw material type.' }
                          )}
                          className="px-3 py-1 rounded border border-red-300 text-xs text-red-700 hover:bg-red-50"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* RECIPES - RIGHT COLUMN */}
        <div className="border  border-gray-400 rounded-lg p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="font-medium">Recipes</h2>
            <button
              type="button"
              onClick={openAddRecipeModal}
              className="bg-[#245658] text-white px-4 py-2 rounded"
            >
              + Add Recipe
            </button>
          </div>

          <div className="mt-4 rounded-md p-3 bg-slate-50">
            <p className="text-sm font-medium text-slate-700 mb-2">
              Available Recipes ({recipes.length})
            </p>
            {recipes.length === 0 ? (
              <p className="text-sm text-slate-500">No recipes found.</p>
            ) : (
              <div className="space-y-3">
                {recipes.map((recipe) => (
                  <div key={recipe.id} className="border border-slate-200 rounded-md p-3 bg-white">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-medium text-slate-800">{recipe.name}</p>
                      <div className="flex flex-col items-end gap-2">
                        <p className="text-xs text-slate-500">
                          Last Modified: {formatDateTimeIST(recipe.last_modified_at || recipe.created_at)}
                        </p>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => requestPin(
                              () => openEditRecipeModal(recipe),
                              { title: 'PIN Required', message: 'Enter PIN to edit (1234) recipe.' }
                            )}
                            className="px-3 py-1 rounded border border-gray-400 text-xs text-gray-800 hover:bg-gray-100"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => requestPin(
                              () => deleteRecipe(recipe),
                              { title: 'PIN Required', message: 'Enter PIN to delete recipe.' }
                            )}
                            className="px-3 py-1 rounded border border-red-300 text-xs text-red-700 hover:bg-red-50"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                      {Array.isArray(recipe.materials) ? recipe.materials.length : 0} materials
                    </p>
                    <ul className="list-disc ml-5 mt-2 space-y-1 text-slate-700 text-sm">
                      {(recipe.materials || []).map((item) => (
                        <li key={`${recipe.id}-${item.id || `${item.rm_name}-${item.quantity}`}`}>
                          {item.rm_name}: {item.quantity} kg
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

              <div className="border border-gray-400 rounded-lg p-4 ">
        <h2 className="font-medium mb-3">Product Types</h2>

        <div className="mt-4 rounded-md p-3 bg-slate-50">
          <p className="text-sm font-medium text-slate-700 mb-2">
            Available Product Types ({productTypes.length})
          </p>
          {productTypes.length === 0 ? (
            <p className="text-sm text-slate-500">No product types found.</p>
          ) : (
            <ul className="space-y-2 text-slate-700">
              {productTypes.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-2 border border-slate-200 rounded-md bg-white px-3 py-2">
                  <div>
                    <span>{t.name}</span>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <p className="text-xs text-slate-500">
                      Last Modified: {formatDateTimeIST(t.last_modified_at || t.created_at)}
                    </p>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => requestPin(
                          () => openEditProductTypeModal(t),
                          { title: 'PIN Required', message: 'Enter PIN to edit (1234) product type.' }
                        )}
                        className="px-3 py-1 rounded border border-gray-400 text-xs text-gray-800 hover:bg-gray-100"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => requestPin(
                          () => deleteProductType(t),
                          { title: 'PIN Required', message: 'Enter PIN to delete product type.' }
                        )}
                        className="px-3 py-1 rounded border border-red-300 text-xs text-red-700 hover:bg-red-50"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      </div>



      <Modal open={showAddRecipe} onClose={closeRecipeModal} title={editingRecipeId ? "Edit Recipe" : "Add Recipe"}>
        <form onSubmit={handleSaveRecipe} className="space-y-4 relative">
          {recipeError && (
            <div className="bg-red-100 text-red-800 px-4 py-3 rounded-lg text-sm border border-red-300">
              {recipeError}
            </div>
          )}
          <div>
            <label className="block text-sm text-black mb-1">Recipe Name (Product Name)</label>
            <input
              type="text"
              value={recipeForm.name}
              onChange={(e) => setRecipeForm((prev) => ({ ...prev, name: e.target.value }))}
              className="w-full px-3 py-2 rounded border border-gray-300"
              placeholder="Enter recipe name"
              required
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="block text-sm text-black">Raw Materials</label>
              <button
                type="button"
                onClick={addRecipeRow}
                className="px-2 py-1 rounded border border-gray-600 text-sm text-black"
              >
                + Add Material
              </button>
            </div>

            {recipeForm.materials.map((material, index) => (
              <div key={`recipe-material-${index}`} className="grid grid-cols-1 md:grid-cols-12 gap-2 items-end">
                <div className="md:col-span-7">
                  <label className="block text-xs text-black mb-1">Raw Material</label>
                  <select
                    value={material.rm_name}
                    onChange={(e) => updateRecipeRow(index, "rm_name", e.target.value)}
                    className="w-full px-3 py-2 rounded border border-gray-300"
                    required
                  >
                    <option value="">Select</option>
                    {rmTypes.map((rm) => (
                      <option key={`recipe-rm-${rm.id || rm.name}`} value={rm.name}>
                        {rm.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="md:col-span-4">
                  <label className="block text-xs text-black mb-1">Weight (kg)</label>
                  <input
                    type="number"
                    step="any"
                    min="0"
                    value={material.quantity}
                    onChange={(e) => updateRecipeRow(index, "quantity", e.target.value)}
                    className="w-full px-3 py-2 rounded border border-gray-300"
                    required
                  />
                </div>
                <div className="md:col-span-1">
                  <button
                    type="button"
                    onClick={() => removeRecipeRow(index)}
                    className="w-full px-2 py-2 rounded border border-gray-600 text-black text-sm"
                  >
                    X
                  </button>
                </div>
              </div>
            ))}
          </div>

          {editingRecipeId && recipeForm.created_at && (
            <div className="absolute bottom-4 right-4 text-xs text-slate-500">
              Created: {formatDateTimeIST(recipeForm.created_at)}
            </div>
          )}

          <div className="flex gap-2 mt-8">
            <button type="submit" className="px-4 py-2 rounded bg-[#245658] text-white">
              {editingRecipeId ? "Update Recipe" : "Save Recipe"}
            </button>
            <button type="button" onClick={closeRecipeModal} className="px-4 py-2 rounded border border-gray-400">
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      <Modal open={showEditRmType} onClose={closeEditRmTypeModal} title="Edit Raw Material Type">
        <form onSubmit={saveRmTypeEdit} className="space-y-4 relative">
          {rmTypeError && (
            <div className="bg-red-100 text-red-800 px-4 py-3 rounded-lg text-sm border border-red-300">
              {rmTypeError}
            </div>
          )}
          <div>
            <label className="block text-sm text-black mb-1">Raw Material Type Name</label>
            <input
              type="text"
              value={rmTypeFormName}
              onChange={(e) => setRmTypeFormName(e.target.value)}
              className="w-full px-3 py-2 rounded border border-gray-300"
              placeholder="Enter RM type name"
              required
            />
          </div>
          {editingRmType && (
            <div className="absolute bottom-4 right-4 text-xs text-slate-500">
              Created: {formatDateTimeIST(editingRmType.created_at)}
            </div>
          )}
          <div className="flex gap-2 mt-8">
            <button type="submit" className="px-4 py-2 rounded bg-[#245658] text-white">
              Update
            </button>
            <button type="button" onClick={closeEditRmTypeModal} className="px-4 py-2 rounded border border-gray-400">
              Cancel
            </button>
          </div>
        </form>
      </Modal>

      <Modal open={showEditProductType} onClose={closeEditProductTypeModal} title="Edit Product Type">
        <form onSubmit={saveProductTypeEdit} className="space-y-4 relative">
          {productTypeError && (
            <div className="bg-red-100 text-red-800 px-4 py-3 rounded-lg text-sm border border-red-300">
              {productTypeError}
            </div>
          )}
          <div>
            <label className="block text-sm text-black mb-1">Product Type Name</label>
            <input
              type="text"
              value={productTypeFormName}
              onChange={(e) => setProductTypeFormName(e.target.value)}
              className="w-full px-3 py-2 rounded border border-gray-300"
              placeholder="Enter product type name"
              required
            />
          </div>
          {editingProductType && (
            <div className="absolute bottom-4 right-4 text-xs text-slate-500">
              Last Modified: {formatDateTimeIST(editingProductType.last_modified_at || editingProductType.created_at)}
            </div>
          )}
          <div className="flex gap-2 mt-8">
            <button type="submit" className="px-4 py-2 rounded bg-[#245658] text-white">
              Update
            </button>
            <button type="button" onClick={closeEditProductTypeModal} className="px-4 py-2 rounded border border-gray-400">
              Cancel
            </button>
          </div>
        </form>
      </Modal>
{/* password */}

{/* Change PIN Button */}

      <PopupDialog
        open={Boolean(rmTypeToDelete)}
        title="Delete Raw Material Type"
        message={rmTypeToDelete ? `Delete raw material type "${rmTypeToDelete.name}"?` : ""}
        onClose={() => setRmTypeToDelete(null)}
        onConfirm={confirmDeleteRmType}
        confirmText="Delete"
        danger
      />

      <PopupDialog
        open={Boolean(productTypeToDelete)}
        title="Delete Product Type"
        message={productTypeToDelete ? `Delete product type "${productTypeToDelete.name}"?` : ""}
        onClose={() => setProductTypeToDelete(null)}
        onConfirm={confirmDeleteProductType}
        confirmText="Delete"
        danger
      />

      <PopupDialog
        open={Boolean(recipeToDelete)}
        title="Delete Recipe"
        message={recipeToDelete ? `Delete recipe "${recipeToDelete.name}"?` : ""}
        onClose={() => setRecipeToDelete(null)}
        onConfirm={confirmDeleteRecipe}
        confirmText="Delete"
        danger
      />

      <PopupDialog
        open={Boolean(popupMessage)}
        title="Error"
        message={popupMessage}
        onClose={() => setPopupMessage('')}
      />
      {pinDialog}
    </div>
  )
}
